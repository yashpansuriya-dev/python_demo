import os 

# -------------------------------------------------------------------

def list_directory(path: str) -> list:
    """
        It lists all files present
        in directory . 

        Args :
            path (str) : path given by user
    """
    os.chdir(path)
    return os.listdir()

# -------------------------------------------------------------------

def main() -> None:
    """
        Main Function
    """
    path = r'D:\intership_code\first\Day04'
    files = list_directory(path)
    print(files)

# -------------------------------------------------------------------

if __name__ == "__main__":
    main()