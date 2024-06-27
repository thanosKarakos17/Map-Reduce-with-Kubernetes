import io
import os
import subprocess
import sys
import time
from kubernetes import client, config
from minio import Minio
from minio.error import S3Error


class Master:

    def __init__(self, input_file, num_mappers, num_reducers):
        # Configure the Kubernetes client
        config.load_incluster_config()
        self.v1 = client.CoreV1Api()
        self.input_file = input_file
        namespace = 'alpha'  # Replace with your MinIO service namespace if different
        service_name = 'minio-service'  # Replace with your MinIO service name
        service = self.v1.read_namespaced_service(name=service_name, namespace=namespace)
        minio_cluster_ip = service.spec.cluster_ip
        minio_port = service.spec.ports[0].port  # Assuming the MinIO service has a single port
        # MinIO endpoint
        self.minio_endpoint = f"{minio_cluster_ip}:{minio_port}"
        # MinIO access credentials
        self.minio_access_key = "your_minio_access_key"  # Replace with your MinIO access key
        self.minio_secret_key = "your_minio_secret_key"  # Replace with your MinIO secret key
        # Configure MinIO client
        self.minio_client = Minio(
            endpoint=self.minio_endpoint,
            access_key=self.minio_access_key,
            secret_key=self.minio_secret_key,
            secure=False
        )

        self.input_bucket_name = 'input-bucket'
        self.shared_bucket_name = 'worker-shared-bucket'    #bucket names mustn't have underscore _ 
        self.output_bucket_name = 'job-result'
        self.completion_bucket_name = 'completion-bucket'
        for bucket_name in [self.input_bucket_name, self.shared_bucket_name, self.output_bucket_name, self.completion_bucket_name]:
            found = self.minio_client.bucket_exists(bucket_name)
            if not found:
                self.minio_client.make_bucket(bucket_name)
                print("Created bucket", bucket_name)
            else:
                print("Bucket", bucket_name, "already exists removing data inside")
                for obj in self.minio_client.list_objects(bucket_name, recursive=True):
                    self.minio_client.remove_object(bucket_name, obj.object_name)
            
        self.num_mappers = num_mappers
        self.num_reducers  = num_reducers


    def create_worker_pod(self, worker_id, num_reducers, task_type):
        pod_id = worker_id if task_type == 'map' else self.num_mappers + worker_id
        pod_name = f"worker-{pod_id}"
        container_name = f"worker-container-{pod_id}"
        
        # Kubernetes pod definition
        pod_manifest = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": pod_name,
                "namespace": "alpha",
                "labels": {
                    "app": "worker",
                    "worker-id": str(pod_id)
                },
                "annotations": {
                    "restarts": "0"  # Initialize restart count
                }
            },
            "spec": {
                "containers": [
                    {
                        "name": container_name,
                        "image": "thkarakos/worker-image",  # Replace with your worker Docker image
                        "command": ["python", "worker.py"],
                        "env": [
                            {"name": "WORKER_ID", "value": str(worker_id)},
                            {"name": "NUM_MAPPERS", "value": str(self.num_mappers)},
                            {"name": "NUM_REDUCERS", "value": str(num_reducers)},
                            {"name": "TASK_TYPE", "value": task_type},
                            {"name": "MINIO_ENDPOINT", "value": self.minio_endpoint},
                            {"name": "MINIO_ACCESS_KEY", "value": self.minio_access_key},
                            {"name": "MINIO_SECRET_KEY", "value": self.minio_secret_key}
                            # Add more environment variables as needed
                        ]
                    }
                ]
            }
        }
        
        # Create the pod
        self.v1.create_namespaced_pod(namespace="alpha", body=pod_manifest)
        print(f"Worker pod {pod_name} created for {task_type}")


    def create_worker(self, partition, id):
        # Logic to create worker pod
        data_str = str(partition)
        data_bytes = io.BytesIO(data_str.encode())
        self.minio_client.put_object(self.input_bucket_name, f"file_{id}.txt", data_bytes, len(data_str), metadata={"status": "uploaded"})
        #check_minio_completion(input_bucket_name, f"file_{id}.txt")
        #worker = Worker(id, num_reducers, 'map')
        self.create_worker_pod(id, self.num_reducers, 'map')
        #print(f"Worker id: {id} created")

    def distribute_tasks(self, input_file_path):
        with open(input_file_path, 'r') as text:
            lines = text.readlines()
            part_size = len(lines) // self.num_mappers
            remainder = len(lines) % self.num_mappers
            start_idx = 0
            id = 0
            for i in range(self.num_mappers):
                end_idx = start_idx + part_size + (1 if i < remainder else 0)
                partition = ''.join(lines[start_idx:end_idx])
                start_idx = end_idx
                self.create_worker(partition, id)
                id += 1

    def check_pod_status(self, pod_name, namespace="alpha"):
        try:
            pod = self.v1.read_namespaced_pod(name=pod_name, namespace=namespace)
        except client.exceptions.ApiException as e:
            print(f"Pod {pod_name} doesn't exist anymore")
            return None
        check = pod.status.container_statuses
        return check[0].last_state.terminated if check is not None else check
        
    def delete_pod(self, pod_name, namespace="alpha"):
        try:
            self.v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
            print(f"Pod {pod_name} deleted.")
        except client.exceptions.ApiException as e:
            print(f"Exception when deleting pod: {e}")

    def wait_for_pod_completion(self, num, namespace="alpha", check_interval=5):
        offset = 0 if num == self.num_mappers else self.num_mappers
        exitcount = [False for i in range(num)]
        while True:

            if exitcount == [True for i in range(num)]: 
                print('Exiting...')
                break
            names = [f"worker-{i+offset}" for i in range(num)]
            status = [self.check_pod_status(pod_name, namespace) for pod_name in names]
            for i in range(len(status)):
                if status[i] is not None and not exitcount[i] and status[i].exit_code == 0 and status[i].reason == 'Completed':
                    print(f"Pod {names[i]} has completed")
                    self.delete_pod(names[i], namespace)
                    exitcount[i] = True
                elif exitcount[i]:
                    print(f"Pod {names[i]} has completed and waiting the others to complete")
                else:
                    print(f"Pod {names[i]} is still doing something")
            time.sleep(check_interval)

    def proceed_to_reduce(self):
        found = self.minio_client.bucket_exists(self.completion_bucket_name)
        if not found:
            self.minio_client.make_bucket(self.completion_bucket_name)
            print("Created bucket", self.completion_bucket_name)
        else:
            print("Bucket", self.completion_bucket_name, "already exists removing data inside")
            for obj in self.minio_client.list_objects(self.completion_bucket_name, recursive=True):
                self.minio_client.remove_object(self.completion_bucket_name, obj.object_name)

    def master_start(self):
        self.distribute_tasks(self.input_file)
        
        self.wait_for_pod_completion(self.num_mappers)
        print('MAP & SHUFFLE COMPLETE!')
        
        print('Now the reducers')
        self.proceed_to_reduce()
        for i in range(self.num_reducers):
            #worker = Worker(i, num_reducers, 'reduce')
            self.create_worker_pod(i, self.num_reducers, 'reduce')
        
        self.wait_for_pod_completion(self.num_reducers)
        
        print('REDUCE COMPLETE!')
        
        objects = self.minio_client.list_objects(self.output_bucket_name, recursive=True)
        for obj in objects:
            # Retrieve each object's data
            data = self.minio_client.get_object(self.output_bucket_name, obj.object_name)
            file_content = data.read().decode('utf-8')
            # Print file name and content
            print(f"File Name: {obj.object_name}")
            print("File Content:")
            print(file_content)
            

if __name__ == '__main__':
    filename = str(sys.argv[1])
    n_map = int(sys.argv[2])
    n_red = int(sys.argv[3])
    mymaster = Master(filename, n_map, n_red)
    mymaster.master_start()
            