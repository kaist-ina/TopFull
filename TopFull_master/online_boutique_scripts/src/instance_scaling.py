import subprocess

def instance_scaling(instances, namespace):
    services = ['frontend', 'recommendationservice', 'currencyservice', 'paymentservice', 'productcatalogservice',
                'shippingservice', 'redis-cart', 'emailservice', 'checkoutservice', 'adservice', 'cartservice']
    for i, service in enumerate(services):
        num_instance = instances[i]
        subprocess.call("kubectl scale deploy -n {} --replicas={} ".format(namespace, num_instance) + service, shell=True)
    return

if __name__ == "__main__":
    instances = [15,2,3,1,5,1,1,1,5,1,5]
    instance_scaling(instances, "default")