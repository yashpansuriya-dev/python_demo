"""
basic file operations such as
reading a file, reading specific number of lines, writing to a file,
and appending text to a file. It also includes basic exception
handling for cases when a file does not exist.

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
        f = open(file_name, "r")
        text = f.read()
    except FileNotFoundError:
        print("File is not existed")
    else:
        f.close()
        return text


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
        f = open(file_name, "r")
        for i in range(num_of_lines):
            list.append(f.readline())
    except FileNotFoundError:
        print("File is not existed")
    else:
        f.close()
        return list
    

def write_file(file_name: str, text: str):
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
        f = open(file_name, "w")
        f.write(text)

    finally:
        print("Text Written Succesfully")
        f.close()
    

def append_file(file_name : str, text: str):
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
        f = open(file_name, "a")
        f.write(text)
    finally:
        print("Text Append Succesfully")
        f.close()

# -------------------------------------------------------------------

def main() -> None:

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

# -------------------------------------------------------------------

if __name__ == "__main__":
    main()