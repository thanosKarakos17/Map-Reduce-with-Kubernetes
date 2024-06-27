import subprocess
import threading
import time
from minio import Minio
from kubernetes import client, config


class Job:
    def __init__(self, input_file, filename, num_mappers, num_reducers):
        self.input_file = input_file
        self.filename = filename
        self.output_file = 'job_result.txt'
        self.mappers = num_mappers
        self.reducers = num_reducers
        self.output_bucket_name = 'job-result'
        self.process2 = None
        
        
    def job_start(self):
        path = 'master-deployment.yaml'
        return self.create_deployment_from_yaml(path)
        #self.mymaster = Master(self.input_file, self.mappers, self.reducers)
        #self.mymaster.master_start()

    def create_deployment_from_yaml(self, manifest_file):
        config.load_incluster_config()  
        self.v1 = client.CoreV1Api()

        try:
            
            process = subprocess.run(['kubectl', 'apply', '-f', manifest_file], check=True)
            print(f"Successfully applied {manifest_file}")
        except subprocess.CalledProcessError as e:
            print(f"Error applying {manifest_file}: {e}")

        while True:
            pod_list = self.v1.list_namespaced_pod(namespace='alpha', label_selector='app=master')
            for pod in pod_list.items:
                name = f"{pod.metadata.name}"
                #print(name)
                #print(f"Pod Name: {pod.metadata.name}")
                #print(f"Pod Status: {pod.status.phase}")
                if pod.status.phase == 'Running':
                    return name
                
    def execute_parallel(self, master_name):

        process0 = subprocess.run(['kubectl', 'cp', './'+self.input_file, master_name+':/app/'+self.filename], check=True)
        print('finito')
        try:
            execute_master = f"python master_pod.py {self.filename} {self.mappers} {self.reducers}"
            # Run kubectl apply -f <manifest_file>
            process = subprocess.run(['kubectl', 'exec', '-it', str(master_name), "--", "/bin/bash", "-c", execute_master], check=True)
            print(f"Successfully applied ")
        except subprocess.CalledProcessError as e:
            print(f"Error applying : {e}")
       
    def get_result(self):
        
        output_bucket_name = 'job-result'
        # MinIO endpoint
        namespace = 'alpha'  # Replace with your MinIO service namespace if different
        service_name = 'minio-service'  # Replace with your MinIO service name
        service = self.v1.read_namespaced_service(name=service_name, namespace=namespace)
        minio_cluster_ip = service.spec.cluster_ip
        minio_port = service.spec.ports[0].port  # Assuming the MinIO service has a single port
        # MinIO endpoint
        minio_endpoint = f"{minio_cluster_ip}:{minio_port}"
        # MinIO access credentials
        minio_access_key = "your_minio_access_key"  # Replace with your MinIO access key
        minio_secret_key = "your_minio_secret_key"  # Replace with your MinIO secret key
        # Configure MinIO client
        
        minio_client = Minio(
            endpoint=minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=False)
            
        objects = minio_client.list_objects(output_bucket_name, recursive=True)
        for obj in objects:
            # Retrieve each object's data
            data = minio_client.get_object(output_bucket_name, obj.object_name)
            file_content = data.read().decode('utf-8')
            yield file_content
    
    def run(self):
        name = self.job_start()
        self.execute_parallel(name)
        res = self.get_result()
        return list(res)

if __name__ == '__main__':
    job = Job('hello.txt', 'hello.txt', 3, 2)
    result = job.run()
    print(str(result))
    exit(0)
    
    
    