# print("\n\n\n -------Login System ----------\n")

# #List of Existing Users and their information
# details = [ {'user':"yash123" , 'passw':"yashyash"}]


# i_user = input("Enter username")

# for detail in details:
#     if detail['user'] == i_user: #It checks is user exists 
#         p_user = input("Plase Enter your Password")
#         if detail['passw'] == p_user: #Checks Password
#             print("You are succesfully logged in")
#         else:
#             print("Wrong Passowrd")
#     else:
#         print("User doesn't exist")

#_-----------------------------------------------------
"""
Simple login system with basic user validation.

Follows:
- Proper naming conventions
- Modular functions
- PEP8 formatting
- Docstrings and comments
"""

USERS = [
    {"username": "yash123", "password": "yashyash"}
]


def find_user(username: str) -> dict | None:
    """
    Search for a user in the USERS list.

    Args:
        username (str): Username entered by the user.

    Returns:
        dict | None: User dictionary if found, otherwise None.
    """
    for user in USERS:
        if user["username"] == username:
            return user
    return None


def login() -> None:
    """
    Handle the login flow:
    - Ask for username
    - Validate user existence
    - Ask for password
    - Validate password
    """
    print("\n" + "-" * 7 + " Login System " + "-" * 7)

    input_username = input("Enter username: ").strip()
    user = find_user(input_username)

    if user is None:
        print("User does not exist.")
        return

    input_password = input("Enter password: ").strip()

    if user["password"] == input_password:
        print("You are successfully logged in.")
    else:
        print("Wrong password.")


if __name__ == "__main__":
    login()
