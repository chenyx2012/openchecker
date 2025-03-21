## Install NFS First (Include server and client)
1. Install the NFS server software
    ```bash
    sudo apt-get update
    sudo apt-get install nfs-kernel-server nfs-common
    ```
2. Create a shared directory
    ```bash
    sudo mkdir /shared_folder
    # Configure the directory permissions to 77x
    sudo chmod 77x /shared_folder -R
    ```
3. Configure the NFS server:  
    Edit the NFS server configuration file /etc/exports:
    ```bash
    sudo nano /etc/exports
    ```
    Add the following line to the file:
    ```bash
    /shared_folder  <client_ip>(rw,sync,no_subtree_check)
    ```
    Replace <client_ip> with the IP address of the client that is allowed to access this shared directory. If you want to allow all clients to access, you can use * instead.
    You can add multiple shared directories, with each directory on a separate line.

4. Export the shared directory:  
    Run the following command to make the NFS server load the new configuration:
    ```bash
    sudo exportfs -a
    ```
    Start the NFS server:
    ```bash
    sudo systemctl start nfs-kernel-server
    ```
    This will start the NFS server and make the shared directory accessible to clients.

## Install NFS-Provisioner
Refer to https://github.com/kubernetes-sigs/nfs-subdir-external-provisioner


## FAQ
- mount: /mnt/nfs: bad option; for several filesystems (e.g. nfs, cifs) you might need a /sbin/mount.<type> helper program  
Check if the nfs-common or nfs-utils components are installed

    ```bash
    sudo apt-get install nfs-common -y
    # or
    sudo apt-get install nfs-utils -y
    ``` 