"""
Defining and Calling Functions
 
def, return, parameters, default arguments, *args, **kwargs, variable scope (local vs global)
 
Write functions: basic calculator, temperature converter, palindrome checker
"""

# ---------------------------------------------------------------------

import string

# ---------------------------------------------------------------------

def cal_add(num_1: int, num_2: int) -> int :
    """
        Function to Add numbers.

        Args : 
            num_1 (int) : First number
            num_2 (int) : Second number
        
        Returns :
            int : returns sum of both numbers

    """
    return num_1+num_2

def cal_sub(num_1: int, num_2: int) -> int :
    """
        Function to Substract numbers.

        Args : 
            num_1 (int) : First number
            num_2 (int) : Second number
        
        Returns :
            int : returns num1 - num2

    """
    return num_1-num_2

def cal_mul(num_1: int, num_2: int) -> int :
    """
        Function to Multiply numbers.

        Args : 
            num_1 (int) : First number
            num_2 (int) : Second number
        
        Returns :
            int : returns multiplication of both numbers

    """
    return num_1*num_2

def cal_div(num_1: int, num_2: int) -> float :
    """
        Function to Divide numbers.

        Args : 
            num_1 (int) : First number
            num_2 (int) : Second number
        
        Returns :
            int : returns num1 / num2

    """
    return num_1/num_2

def cal_rem(num_1: int, num_2: int) -> int :
    """
        Function to get remainder of when divide 
        both numbers

        Args : 
            num_1 (int) : First number
            num_2 (int) : Second number
        
        Returns :
            int : returns remainder when num1/num2

    """
    return num_1%num_2

def cal_pow(num_1: int, num_2: int) -> int :
    """
        Returns power of num1 as base , 
                        num2 as power.

        Args : 
            num_1 (int) : First number
            num_2 (int) : Second number
        
        Returns :
            int : returns num1 ^ num2

    """
    return num_1**num_2

def calculator() -> None :
    """
        Function to Perform all basic operation of calculator . 
        Add , Substraction , Multiplication , Divide , Power
        , Remainder.

    """
    c = None
    while(c != 0):
        print("\n 1 : Add ")
        print("2 : Substract ")
        print("3 : Multiply ")
        print("4 : Divide ")
        print("5 : Remainder ")
        print("6 : Power ")
        c = int(input("Please Choose Operation"))

        num_1 = int(input("Enter First number : "))
        num_2 = int(input("Enter Second number : "))

        if c == 0:
            print("Thank You ! for using our calculator")
            break
        elif c == 1:
            print("Sum is : ",cal_add(num_1,num_2))
        elif c == 2:
            print("Substraction is : ",cal_sub(num_1,num_2))       
        elif c == 3:
            print("Multiplication is : ",cal_mul(num_1,num_2))        
        elif c == 4:
            print("Division is : ",cal_div(num_1,num_2))       
        elif c == 5:
            print("Remainder is : ",cal_rem(num_1,num_2))
        elif c == 6:
            print("Power is : " ,cal_pow(num_1,num_2))

# ---------------------------------------------------------------------

# Example of *args , Used when no. of parameters are not fixed .
def add_numbers(*numbers: int) -> int:
    """
        Add function , but here no. of parameters are not
        restricated . 

        Args :
            numbers (int) : all number that needs to be sumed.
        
        Returns :
            int : returns sum of all numbers
    """
    sum = 0
    for number in numbers:
        sum = sum + number
    
    return sum

# Use of **Kwargs , Here parameters are in key-value Pair
def print_details(**student) -> None:
    """
        Print details of student , and args passed 
        in key-value manner .

        Args :
            student : details of student
    """
    print("Name :" , student['name'])
    print("Roll no :" , student['roll_no'])
    print("Marks :" , student['marks'])

# Use of Default Parameter , take default when parameter is not passed .
def greet_user(name : string = "User") -> None:
    """
        Greets User , with specified name and
        if name not specified it takes as 'User'.

        Args :
            name : takes name or by default 'User'.
    """
    print(f"Hello ! {name}")


def is_palindrome(data : string) -> bool :
    """
        Checks if , given string  
        is palindrome or not . 

        Args :
            data (string) : Input String

        Returns :
            bool : returns True if string is palindrome
                    otherwise False

    """
    data = data.lower()
    return data == data[::-1] # Compare String with its reverse

def celcius_tofarenheit(cel : float) -> float :
    """
        Converts Celcius temprature into Farenhit 

        Args :
            cel (float) : Input temprature in celcius 
        
        Returns :
            float : returns Farenhit .
    """
    return (cel * 1.8)+32

def farenheit_tocelcius(f : float) -> float :
    """
        Converts Farenhit into celcius .

        Args :
            f (float) : Input temprature in Farenhit
        
        Returns :
            float : returns Celcius .
    """
    return (f-32)/1.8

# ---------------------------------------------------------------------

def main() -> None :
    # print("HI")

    # No of arguments not fixed.
    print("Sum of All numbers is : ",add_numbers(1,2,3,4))

    #If args not passed by default takes 'User'
    greet_user("Sahil")

    #args in key-value pair
    print_details("\nDetails are : ",name="yash",roll_no=4,marks=89)

    print("\nIs it palindrome : ",is_palindrome("YaaY"))

    print("Calcius to Farenhit : ",celcius_tofarenheit(34), "F.")
    print("Farenhit to Calcius : ",farenheit_tocelcius(100), "C")

    calculator()

# ---------------------------------------------------------------------

if __name__ == "__main__":
    main()

