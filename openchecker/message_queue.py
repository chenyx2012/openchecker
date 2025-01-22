import pika
from helper import read_config
import logging

def test_rabbitmq_connection(config):
    credentials = pika.PlainCredentials(config['username'], config['password'])
    parameters = pika.ConnectionParameters(config['host'], int(config['port']), '/', credentials)

    try:
        connection = pika.BlockingConnection(parameters)
        connection.close()
        logging.info("RabbitMQ connection successful.")
    except Exception as e:
        logging.info(f"Error connecting to RabbitMQ: {str(e)}")

def create_queue(config, queue_name, arguments={}):
    credentials = pika.PlainCredentials(config['username'], config['password'])
    parameters = pika.ConnectionParameters(config['host'], int(config['port']), '/', credentials)

    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        queue = channel.queue_declare(queue=queue_name, arguments=arguments, passive=True)
        logging.info("Queue {} exists, pass creating!".format(queue_name))

    except pika.exceptions.ChannelClosed as e:
        logging.info("Queue {} does not exist, created!".format(queue_name))
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        queue = channel.queue_declare(queue=queue_name, arguments=arguments)
    except Exception as e:
        logging.info(f"Error connecting to RabbitMQ: {str(e)}")
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
        logging.info(f"Publish message successed!")
        return None
    except Exception as e:
        logging.info("Publish message failed as: {}".format(e))
        return str(e)

def consumer(config, queue_name, callback_func):
    credentials = pika.PlainCredentials(config['username'], config['password'])
    parameters = pika.ConnectionParameters(config['host'], int(config['port']), '/', credentials, heartbeat=config['heartbeat_interval_s'], blocked_connection_timeout=config['blocked_connection_timeout_ms'])

    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue=queue_name, on_message_callback=callback_func, auto_ack=False)
        logging.info('Consumer connected, wating for messages...')
        channel.start_consuming()

    except Exception as e:
        logging.info("Consumer failed as: {}".format(e))
        return str(e)

def check_queue_status(config, queue_name):
    credentials = pika.PlainCredentials(config['username'], config['password'])
    parameters = pika.ConnectionParameters(config['host'], int(config['port']), '/', credentials)

    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        queue_declaration = channel.queue_declare(queue=queue_name, passive=True)
        messages_in_queue = queue_declaration.method.message_count
        consumers_on_queue = queue_declaration.method.consumer_count

        connection.close()
        return messages_in_queue, consumers_on_queue
    except Exception as e:
        logging.info(f"Error checking queue status: {str(e)}")
        return None, None

def get_queue_info(config, queue_name):
    credentials = pika.PlainCredentials(config['username'], config['password'])
    parameters = pika.ConnectionParameters(config['host'], int(config['port']), '/', credentials)

    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        queue_declaration = channel.queue_declare(queue=queue_name, passive=True)
        queue_arguments = queue_declaration.method.arguments

        connection.close()
        return queue_arguments
    except Exception as e:
        logging.info(f"Error getting queue info: {str(e)}")
        return None

def view_queue_logs(log_file_path):
    try:
        with open(log_file_path, 'r') as log_file:
            logs = log_file.readlines()
            queue_logs = [log for log in logs if "Queue" in log]
            return queue_logs
    except Exception as e:
        logging.info(f"Error viewing queue logs: {str(e)}")
        return None

def delete_queue(config, queue_name):
    credentials = pika.PlainCredentials(config['username'], config['password'])
    parameters = pika.ConnectionParameters(config['host'], int(config['port']), '/', credentials)

    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.queue_delete(queue=queue_name)
        connection.close()
        logging.info(f"Queue {queue_name} deleted successfully.")
    except Exception as e:
        logging.info(f"Error deleting queue {queue_name}: {str(e)}")

def purge_queue(config, queue_name):
    credentials = pika.PlainCredentials(config['username'], config['password'])
    parameters = pika.ConnectionParameters(config['host'], int(config['port']), '/', credentials)

    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.queue_purge(queue=queue_name)
        connection.close()
        logging.info(f"Queue {queue_name} purged successfully.")
    except Exception as e:
        logging.info(f"Error purging queue {queue_name}: {str(e)}")

if __name__ == "__main__":
    config = read_config('config/config.ini', "RabbitMQ")
    test_rabbitmq_connection(config)
