'''
 A Phonebook app , which has Functionality of Add , Delete , Search and
 List of Contacts .
'''
# ----------------------------------------------------------------------

import string

# ---------------------------------------------------------------------

# All Functions of Phonebook - add , delete , list , search


# Add contact function
def phonebook_add(name: string, number: string, contacts: list) -> list:
    """
        It takes name and mobile number from user , and
        add it in contact list .

        Args :
            name (string) : Name of contact.
            number (string) : Mobile number of that contact.
            contact (list) : list containing all contacts.

        Returns :
            list : returns list containing all contacts .

    """
    if (len(number) == 10):  # It add contact only if digit is 10 .
        contacts.append({'name': name, 'number': number})
    else:
        print("Mobile number should be 10 digit .")


# Searching contact
def phonebook_search(name: string, contacts: list) -> dict:
    """
        It Serch the contact of input name and
        print its info . name and mobile number.

        Args :
            name (string) : takes name as input from user

        Returns :
            contacts (list) : list containing all contacts .
    """

    print("Here is detail of ", name)
    

    for c in contacts:
        # Iterates through all contacts and print who matches name

        if c['name'] == name:
            print(f"\n Name : {c['name']}, Mobile number : {c['number']}")
            return c
        else:
            pass

    print("Wrong name ! , Please Enter correct name")


# List contact
def phonebook_list(contacts: list) -> None:
    """
        It prints all the info of contacts ,
        name and mobile number .

        Args :
            contacts (list) : list containing all contacts.

        Returns :
            None : It just prints .
    """
    print("Here are Contacts ")

    for c in contacts:
        # Prints every contact
        print(f" Name : {c['name']}  , Mobile number : +91 {c['number']}")


# Deleting Contact
def phonebook_del(name: string, contacts: list) -> dict:
    """
        It delete the record of that contact
        that user sends name as input .

        Args :
            name (string) : name of user that needs to be deleted
            contacts (list) : list containing all contacts

        Returns :
            dict : deleted contact .
    """
    del_contact = phonebook_search(name, contacts)
    contacts.remove(del_contact)  # remove the dict contact
    return del_contact

# ---------------------------------------------------------------------

def main() -> None:
    contacts = []
    c = 1
    while (c != 0):
        print("\nWelcome to Phone Book ")
        print("Press 0 : exit")
        print("Press 1 : List Contact")
        print("Press 2 : Add Contact")
        print("Press 3 : Search Contact")
        print("Press 4 : Delete Contact")

        c = int(input("Enter Your Choice : "))

        if c == 0:
            print("Thank You , for using phonebook .")
            break
        elif c == 1:
            phonebook_list(contacts)

        elif c == 2:
            name = input("Please Enter your name : ")
            number = input("Please Enter your name : ")
            phonebook_add(name, number, contacts)

        elif c == 3:
            name = input("Please Enter your name : ")
            phonebook_search(name, contacts)

        elif c == 4:
            name = input("Please Enter your name : ")
            phonebook_del(name, contacts)

# ---------------------------------------------------------------------


if __name__ == "__main__":
    main()
