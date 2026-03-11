"""
It demonstrates basic file operations in Python such as
reading a file, reading specific number of lines, writing to a file,
and appending text to a file. It also includes basic exception
handling for cases when a file does not exist.

With help of context manager in file handling . 


"""

# -------------------------------------------------------------------

def read_file(file_name : str) -> str:
    """
       It reads file and returns data of file . 
       and raise error if file not existed

       Args :
        file_name (str) : name of file

       Returns :
        str : text of file
    """
    try:
        with open(file_name, "r") as f:
            return f.read()
    except FileNotFoundError:
        print("File is not existed")

def read_lines(file_name : str, num_of_lines: int) -> list:
    """
        It opens file and returns list of lines 
        with provided no. of lines . 

        Args : 
            file_name (str) : name of file
            num_of_lines (int) : no. of lines to fetch
        
        Returns :
            list : list containing lines.
    """

    list = []
    try:
        with open(file_name, "r") as f:
            for i in range(num_of_lines):
                list.append(f.readline())
    except FileNotFoundError:
        print("File is not existed")
    else:
        return list
    
def write_file(file_name: str, text: str) -> str:
    """
        It opens file or create if not exist
        and overwrite text of file.
        Note : To create empty file pass ""
        as text . 

        Args : 
            file_name (str) : name of file
            text (str) : text to write
    """
    try:
        with open(file_name, "w") as f:
            f.write(text)
    finally:
        print("Text Written Succesfully")
    

def append_file(file_name : str, text: str) -> str:
    """
        It opens file or create if not exist
        and append text of file.
        Note : To create empty file pass ""
        as text . 

        Args : 
            file_name (str) : name of file
            text (str) : text to write
    """
    try:
        with open(file_name, "a") as f:
            return f.write(text)
    finally:
        print("Text Append Succesfully")

# -------------------------------------------------------------------

def main() -> None:
    print("hello")


    text = "Python is one of the most popular programming languages.\n " \
    "It’s simple to use, packed with features and supported by a wide\n " \
    "range of libraries and frameworks. Its clean syntax makes it\n " \
    "beginner-friendly."

    write_file("newfile_2.txt", text)

    print("new_file2.txt : ", read_file("newfile_2.txt"))

    print("\n Two Line : ", read_lines("newfile_2.txt", 2))


    new_text = "\nData Structures \nPython offers versatile collections\n " \
    "of data types, including lists, string, tuples, sets, dictionaries\n" \
    " and arrays. In this section, we will learn about each data types " \
    "in detail"

    print("\nAppending new Text : ")
    append_file("newfile_2.txt", new_text)

    print("\n\nnew_file2.txt : ", read_file("newfile_2.txt"))

def main2():
    print("hello")
    with open("file.txt" , "w") as f:
        f.write("yash\n4")
    
    with open("file.txt" , "rb") as f:
        print(f.read(1)[0])
    

# -------------------------------------------------------------------


if __name__ == "__main__":
    main2()