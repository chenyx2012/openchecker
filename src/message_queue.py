import pika
from helper import read_config

def test_rabbitmq_connection(config):
    credentials = pika.PlainCredentials(config['username'], config['password'])
    parameters = pika.ConnectionParameters(config['host'], int(config['port']), '/', credentials)

    try:
        connection = pika.BlockingConnection(parameters)
        connection.close()
        print("RabbitMQ connection successful.")
    except Exception as e:
        print(f"Error connecting to RabbitMQ: {str(e)}")

def create_queue(config, queue_name):
    credentials = pika.PlainCredentials(config['username'], config['password'])
    parameters = pika.ConnectionParameters(config['host'], int(config['port']), '/', credentials)

    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        queue = channel.queue_declare(queue=queue_name, passive=True)
        print("Queue {} exists, pass creating!".format(queue_name))

    except pika.exceptions.ChannelClosed as e:
        print("Queue {} does not exist, created!".format(queue_name))
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        queue = channel.queue_declare(queue=queue_name)
    except Exception as e:
        print(f"Error connecting to RabbitMQ: {str(e)}")
        exit()

    connection.close()

def publish_message(config, queue_name, message_body):
    credentials = pika.PlainCredentials(config['username'], config['password'])
    parameters = pika.ConnectionParameters(config['host'], int(config['port']), '/', credentials)

    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.basic_publish(exchange='', routing_key=queue_name, body=message_body)
        connection.close()
        print(f"Publish message successed!")
        return None
    except Exception as e:
        print("Publish message failed as: {}".format(e))
        return str(e)

def consumer(config, queue_name, callback_func):
    credentials = pika.PlainCredentials(config['username'], config['password'])
    parameters = pika.ConnectionParameters(config['host'], int(config['port']), '/', credentials, heartbeat=0, blocked_connection_timeout=300000)

    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue=queue_name, on_message_callback=callback_func, auto_ack=False)
        print('Consumer connected, wating for messages...')
        channel.start_consuming()

    except Exception as e:
        print("Consumer failed as: {}".format(e))
        return str(e)

if __name__ == "__main__":
    config = read_config('config/config.ini', "RabbitMQ")
    test_rabbitmq_connection(config)
