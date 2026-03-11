"""
BaseException
│
├── SystemExit
├── KeyboardInterrupt
└── Exception
    ├── ValueError
    ├── TypeError
    ├── IndexError
    ├── KeyError
    ├── FileNotFoundError
    └── ZeroDivisionError
    ├── SyntaxError
            ├── Indetation Error

Source : https://docs.python.org/3/library/exceptions.html#exception-hierarchy

Exception Handling : 
try / except / else / finally, multiple exception types, raise, custom exceptions
Wrap all file operations and user inputs in proper try/except blocks .
"""

# -------------------------------------------------------------------

class CustomException(Exception):
    pass

class InvalidAgeError(Exception):
    pass

# -------------------------------------------------------------------

def divide() -> int:
    print("\nWelcome to Divide Operation .")
    a = int(input("Enter First number : "))
    b = int(input("Enter Second number : "))

    try :
        if b == 0:
            raise ZeroDivisionError("Can't Divide by Zero")
    except ZeroDivisionError:
        print("Can't divide by zero")
    except ArithmeticError:
        print("Arithmetic error occured")
    else:
        print("A/B is : ", a/b)
    finally:
        print("Divide operation done . ")
        

def read_file(file_name):
    print("\nReading File...")

    try:
        f = open(file_name , "r")
        text = f.read()
    except FileNotFoundError:
        print("File Does not exist")
    except PermissionError:
        print("File has not permission to read")
    except Exception:
        print("Unanomius except occurs")
    else:
        print("File read Succesfully")
        print(text)
    finally:
        print("File Operation attempted")

def user_age():

    try:
        age = int(input("\nEnter Your age : "))
        if age < 0:
            raise InvalidAgeError("Age Can not be negative")
    except ValueError:
        print("It needs to be number")
    except InvalidAgeError as e:
        print(e)
    else:
        print("Your age is : ", age)
    finally:
        print("Input process finished.\n")

# -------------------------------------------------------------------

def main() -> None:
    divide()

    user_age()

    read_file("myfile.txt")

# -------------------------------------------------------------------

if __name__ == '__main__':
    main()
