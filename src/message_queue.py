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

if __name__ == "__main__":
    config = read_config('config/config.ini')
    test_rabbitmq_connection(config)
