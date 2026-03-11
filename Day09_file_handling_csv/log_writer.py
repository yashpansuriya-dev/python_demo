"""
    It writes log into a file with provided
    message , log type , current timestamp of log .

    For Example,
    2026-03-11 15:24:36.750710 TRACE  :........router_forward_getOI:

"""

# -------------------------------------------------------------------

from datetime import datetime

# -------------------------------------------------------------------

def log_writer(message : str, type_msg: str, file_name: str):
    try: 
        with open(file_name, "a") as f:
            f.write(f"\n{datetime.now()} {type_msg}  :{message}")
    finally:
        print("Log updated succesfully")
    
# -------------------------------------------------------------------

def main() -> None:
    """ Main Function . """

    log_writer("...mailslot_create: creating mailslot for terminate",
               "INFO ",
               "log.txt")   
    log_writer("........router_forward_getOI:         source address:   9.67.116.98",
               "TRACE",
               "log.txt")

# -------------------------------------------------------------------

if __name__ == "__main__":
    main()
