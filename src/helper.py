import configparser

def read_config(filename, modulename=None):
    config = configparser.ConfigParser()
    config.read(filename)
    return config[modulename] if modulename !=None else config