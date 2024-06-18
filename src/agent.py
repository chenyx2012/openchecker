import subprocess
from message_queue import read_config, consumer
import json

def callback_func(ch, method, properties, body):
    message = json.loads(body.decode('utf-8'))
    command = message.get('command')
    project_url = message.get('project_url')
    callback_url = message.get('callback_url')

    if command == 'osv-scanner':

        shell_script=f"""
            project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
            git clone {project_url} > /dev/null
            osv-scanner --format json -r $project_name
            rm -rf $project_name > /dev/null
        """

        process = subprocess.Popen([shell_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        output, error = process.communicate()

        if process.returncode == 0:
            print("osv-scanner job done: {}".format(project_url))
            scan_result = json.loads(output.decode("utf-8"))
            print(scan_result)
        else:
            print("osv-scanner job failed: {}, error: {}".format(project_url, error))

    elif command == 'scancode':

        shell_script=f"""
            project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
            git clone {project_url} > /dev/null
            scancode -lc --json-pp scan_result.json $project_name --unknown-licenses -n 4 > /dev/null
            cat scan_result.json
            rm -rf $project_name scan_result.json > /dev/null
        """

        process = subprocess.Popen([shell_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        output, error = process.communicate()

        if process.returncode == 0:
            print("scancode job done: {}".format(project_url))
            scan_result = json.loads(output.decode("utf-8"))
            print(scan_result)
        else:
            print("scancode job failed: {}, error: {}".format(project_url, error))
    else:
        print(f"Unknown command: {command}")

    ch.basic_ack(delivery_tag=method.delivery_tag)

if __name__ == "__main__":
    config = read_config('config/config.ini')
    consumer(config, "opencheck", callback_func)
    print('Agents are serving. To exit press CTRL+C')
