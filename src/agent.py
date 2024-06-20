import subprocess
from message_queue import read_config, consumer
import json

def shell_exec(shell_script):
    process = subprocess.Popen([shell_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    shell_output, error = process.communicate()

    if process.returncode == 0:
        output = json.loads(shell_output.decode("utf-8"))
        return output, None
    else:
        return output, error

def callback_func(ch, method, properties, body):
    message = json.loads(body.decode('utf-8'))
    command_list = message.get('command_list')
    project_url = message.get('project_url')
    callback_url = message.get('callback_url')
    task_metadata = message.get('task_metadata')

    for command in command_list:
        if command == 'osv-scanner':

            shell_script=f"""
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                git clone {project_url} > /dev/null
                osv-scanner --format json -r $project_name
                rm -rf $project_name > /dev/null
            """

            result, error = shell_exec(shell_script)

            if error == None:
                print("osv-scanner job done: {}".format(project_url))
                print(result)
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

            result, error = shell_exec(shell_script)

            if error == None:
                print("scancode job done: {}".format(project_url))
                print(result)
            else:
                print("scancode job failed: {}, error: {}".format(project_url, error))
        else:
            print(f"Unknown command: {command}")

    ch.basic_ack(delivery_tag=method.delivery_tag)

if __name__ == "__main__":
    config = read_config('config/config.ini')
    consumer(config, "opencheck", callback_func)
    print('Agents are serving. To exit press CTRL+C')
