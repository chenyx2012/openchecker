import configparser
import pika

def read_config(filename):
    config = configparser.ConfigParser()
    config.read(filename)
    return config['RabbitMQ']

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

if __name__ == "__main__":
    config = read_config('config/config.ini')
    test_rabbitmq_connection(config)
