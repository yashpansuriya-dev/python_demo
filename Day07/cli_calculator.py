"""
CLI Calculator App
 
It Support +, -, *, /, %, power, square root; 
loop until user quits; 
and input validation
"""

# -------------------------------------------------------------------

import math

# -------------------------------------------------------------------

max_history = 10

# -------------------------------------------------------------------


def add_history(exp : str , history_list : list) -> None:
    """
    It taken string expression as arg and it in 
    list containing history of past calculations.

    Args :
        exp (str) : expression as string
        history_list (list) : History List

    """ 

    # If list exceeds then 10 , it removes oldest history
    if(len(history_list) < max_history):
        history_list.append(exp)
    else:
        history_list.pop(0)
        history_list.append(exp)


def get_history(history_list : list) -> None:
    """
    It prints Histroy by iterating history_list.

    Args :
        history_list (list) : History List

    """
    for l in history_list:
        print(l)


def get_number(prompt: str) -> float:
    """
    Prompt the user for input and convert it to a float.
    Keeps asking until the user enters a valid numeric value.

    Args:
        prompt (str): Message displayed to the user.

    Returns:
        float: The numeric value entered by the user.
    """
    try:
        return float(input(prompt))
    except ValueError:
        print("Invalid number , Please enter numeric value")
        


def add(a: float, b: float) -> float:
    """
    Return the sum of two numbers.

    Args:
        a (float): First number
        b (float): Second number

    Returns:
        float: Result of a + b
    """
    return a+b


def sub(a: float, b: float) -> float:
    """
    Return the difference between two numbers.

    Args:
        a (float): First number
        b (float): Second number

    Returns:
        float: Result of a - b
    """
    return a-b


def multi(a: float, b: float) -> float:
    """
    Multiply two numbers.

    Args:
        a (float): First number
        b (float): Second number

    Returns:
        float: Result of a * b
    """
    return a*b


def div(a: float, b: float) -> float:
    """
    Divide the first number by the second number.
    Raises an error if the divisor is zero.

    Args:
        a (float): Dividend
        b (float): Divisor

    Returns:
        float: Result of a / b

    Raises:
        ZeroDivisionError: If b is zero.
    """
    if b == 0:
        raise ZeroDivisionError("Can not divide by zero")
    else:
        return a/b


def rem(a: float, b: float) -> float:
    """
    Return the remainder of division between two numbers.

    Args:
        a (float): Dividend
        b (float): Divisor

    Returns:
        float: Result of a % b
    """
    return a%b


def power(a: float, b: float) -> float:
    """
    Raise a number to a given power.

    Args:
        a (float): Base number
        b (float): Exponent

    Returns:
        float: Result of a ** b
    """
    return a**b


def sqrt(a: float) -> float:
    """
    Calculate the square root of a number.

    Args:
        a (float): Number whose square root is needed

    Returns:
        float: Square root of the number
    """
    return math.sqrt(a)


# -------------------------------------------------------------------


def main() -> None :
    """ Main Function ."""
    history_list = []

    print("-----------------------CLI Calculator--------------------")

    c = 1
    while(c != 0):

        print("\nAddition :       1 ")
        print("Substraction :   2 ")
        print("Multiplication : 3 ")
        print("Divide :         4 ")
        print("Remainder :      5 ")
        print("Power :          6 ")
        print("Sqaure root :    7 ")
        print("History  :       8 ")
        print("Exit App       : 0")

        c = int(input("\nEnter Your choice : "))

        if c ==7:
            n = float(input("Enter Number: "))
            print("Your Square root is : ", sqrt(n))
        elif c == 8:
            get_history(history_list)
        elif c == 0:
            break
        else:
            a = get_number("Enter First number : ")
            b = get_number("Enter Second number : ")
            if c == 1:
                val = f"{a} + {b} = {add(a, b)}"
                print(val)
                add_history(val, history_list)
            elif c == 2:
                val = f"{a} - {b} = {sub(a, b)}"
                print(val)
                add_history(val, history_list)
            elif c == 3:
                val = f"{a} * {b} = {multi(a, b)}"
                print(val)
                add_history(val, history_list)
            elif c == 4:
                val = f"{a} / {b} = {div(a, b)}"
                print(val)
                add_history(val, history_list)
            elif c == 5:
                val = f"{a} % {b} = {rem(a, b)}"
                print(val)
                add_history(val, history_list)
            elif c == 6:
                val = f"{a} ^ {b} = {power(a, b)}"
                print(val)
                add_history(val, history_list)
            else:
                print("Invalid Choice")
            
            
# -------------------------------------------------------------------

if __name__ == "__main__":
    main()







