# Map-Reduce-with-Kubernetes

![image](https://github.com/thanosKarakos17/Map-Reduce-with-Kubernetes/assets/103602897/0988df86-af99-4c7e-b731-9cb03a1bc32d)


![image](https://github.com/thanosKarakos17/Map-Reduce-with-Kubernetes/assets/103602897/682f0c58-1892-4c0e-ba95-c0d1fea75702)

docker login to your dockerhub registry \
create namesapce 'alpha'
go to .yaml files and replace our docker_hub_username with your <docker_hub_username> in the image field \
go to master_pod.py in the create_pod function and in the image field place your <docker_hub_username> \
docker build -t <your_username>/worker-image -f Dockerfile-worker \
docker build -t <your_username>/master-image -f Dockerfile-master \
docker build -t <your_username>/flask -f Dockerfile-app \
docker build -t <your_username>/auth-image -f Dockerfile-auth \
docker push <your_username>/worker-image \
docker push <your_username>/master-image \
docker push <your_username>/auth-image \
docker push <your_username>/flask-app \
kubectl apply -f all_files_ending_in.yaml \
kubectl port-forward -n alpha service/flask-app 5000:5000 #in order to have access to user_interface page \
kubectl port-forward -n alpha service/headlamp 8000:80 #in order to open the headlamp dashboard \
kubectl get po -n alpha \
copy the flask-app name \
kubectl exec -it paste_here /bin/bash \
->>python application.py \
open localhost:5000
enjoy the app!
