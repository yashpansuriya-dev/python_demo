# -------------------------------------------------------------------

import string
import random

# -------------------------------------------------------------------
def generate_password(length : int = 12) -> str :
    """
    Generate random password with specified length 
    and returns it . 

    Args :
        length (int) : the length of password
    """
    characters = string.ascii_letters + string.digits + string.punctuation
    password = ""
    for i in range(length):
        letter = random.choice(characters)
        password += letter
    
    return password

def generate_passwords(length :int =12 , n :int = 10) -> list :
    """
        Generate list of passwords with specified numbers . 

        Args :
            length (int) : length of each password
            n (int) : total no of passwords
    """
    passwords = []
    for i in range(n):
        passwords.append(generate_password(length))
    
    return passwords

# -------------------------------------------------------------------

def main() -> None :
    """ Main Function ."""
    print(generate_passwords())
    print("hello")
# -------------------------------------------------------------------

if __name__ == "__main__" :
    main()