from enum import Enum
import io
import os
import re  # package for re.split('\\s+')
import hashlib
from minio import Minio
from minio.error import S3Error


class WORKER_TYPE(Enum):
    IDLE = 0
    MAP = 1
    SHUFFLE = 3
    REDUCE = 3

class Worker:

    def worker_start(self):
        if self.completed_task():
            return
        else:
            if self.what_to_do == 'map':
                self.map_task()
                self._write_completion_flag()
            elif self.what_to_do == 'reduce':
                self.reduce_task()
                self._write_completion_flag()

    def map_task(self):
        in_filename = f"file_{self.id}.txt"
        self.type = WORKER_TYPE.MAP
        partition_lines = self._open_bucket(self.input_bucket, in_filename)
        word_list = re.split('\\s+|,', partition_lines)  # '\\s+' spaces, tabs, and newline characters
        mapped_words = list()
        mapped_words = list(map(lambda single_word: (str(single_word).lower(), 1), word_list))  # creates a list of (word, 1)

        #print(mapped_words)
        self._shuffle_task(mapped_words)
        self.type = WORKER_TYPE.IDLE
        return

    def reduce_task(self):
        self.type = WORKER_TYPE.REDUCE
        client = self.client
        bucket_name = self.bucket_name
        list_of_tuples = []
        for i in range(num_mappers):
            filename = f"file_{self.id}{i}.txt"
            list_of_tuples += self._open_bucket(bucket_name, filename)

        reduce_count = {}

        for key, value in list_of_tuples:
            if key not in reduce_count:
                reduce_count[key] = value
            else:
                reduce_count[key] += value

        reduce_count = list(reduce_count.items())  # covert dictionary to list of tuples

        data_str = str(reduce_count)
        data_bytes = io.BytesIO(data_str.encode())
        client.put_object(self.output_bucket, filename, data_bytes, len(data_str))

        self.type = WORKER_TYPE.IDLE
        return reduce_count

    def _shuffle_task(self, list_of_tuples):
        client = self.client
        bucket_name = self.bucket_name
        self.type = WORKER_TYPE.SHUFFLE
        R = self.num_reducers
        index = 0
        for key, value in list_of_tuples:
            string_token = str(int(hashlib.md5(key.encode()).hexdigest(), 16) % R)
            try:
                token_file_name = f"file_{string_token}{self.id}.txt"
                response = client.get_object(bucket_name, token_file_name)
                existing_data = eval(response.read().decode('utf-8'))
                existing = existing_data if existing_data is not None else []
            except S3Error as err:
                if err.code == 'NoSuchKey':
                    existing = []
                else:
                    raise

            existing.append(list_of_tuples[index])
            data_str = str(existing)
            data_bytes = io.BytesIO(data_str.encode())
            client.remove_object(bucket_name, token_file_name)
            client.put_object(bucket_name, token_file_name, data_bytes, len(data_str))
            index += 1
        return
    
    def _open_bucket(self, bucket, filename):
        response2 = self.client.get_object(bucket, filename).read().decode('utf-8')
        list_of_tuples = eval(response2) if self.type == WORKER_TYPE.REDUCE else response2
        return list_of_tuples
    
    def _write_completion_flag(self):
        flag_name = f"completion_flag_{self.id}.txt"
        data_str = "completed"
        data_bytes = io.BytesIO(data_str.encode())
        #self.client.remove_object('completion-bucket', flag_name)
        self.client.put_object('completion-bucket', flag_name, data_bytes, len(data_str))

    def completed_task(self):
        try:
            self.client.stat_object('completion-bucket', f"completion_flag_{self.id}.txt")
            return True
        except S3Error as e:
            if e.code == 'NoSuchKey':
                return False
        else:
            raise
    
    def get_status(self):
        return f"Worker id: {self.id}, type: {self.type}"


    def __init__(self, worker_id, num_mappers, num_reducers, task)  -> None:
        self.input_bucket = 'input-bucket'
        self.bucket_name = 'worker-shared-bucket'
        self.output_bucket = 'job-result'
        self.id = worker_id
        self.num_mappers = num_mappers
        self.num_reducers = num_reducers
        self.type = WORKER_TYPE.IDLE
        self.client = Minio(endpoint=os.getenv('MINIO_ENDPOINT', ' '),
               access_key=os.getenv('MINIO_ACCESS_KEY', ' '),
               secret_key=os.getenv('MINIO_SECRET_KEY', ' '),
               secure=False
               )
        self.what_to_do = task
        #self.worker_start()

if __name__ == '__main__':
    id = int(os.getenv('WORKER_ID', 0))
    num_mappers = int(os.getenv('NUM_MAPPERS', 3))
    num_reducers = int(os.getenv('NUM_REDUCERS', 2))
    task = str(os.getenv('TASK_TYPE', 'map'))
    worker = Worker(id, num_mappers, num_reducers, task)
    worker.worker_start()