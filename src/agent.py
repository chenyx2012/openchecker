import subprocess
from message_queue import read_config, consumer
import json

def callback_func(ch, method, properties, body):
    message = json.loads(body.decode('utf-8'))
    command = message.get('command')
    
    if command == 'osv-scanner':
        subprocess.call(['osv-scanner'], shell=True)
        print("Run osv-scanner done.")
    elif command == 'scancode':
        subprocess.call(['scancode'], shell=True)
        print("Run scancode done.")
    else:
        print(f"Unknown command: {command}")

if __name__ == "__main__":
    config = read_config('config/config.ini')
    consumer(config, "opencheck", callback_func)
    print('Agents are serving. To exit press CTRL+C')
