"""
    Example of Overridden method and 
    isinstance() method . 
"""
# -------------------------------------------------------------------

class Parent:
    """ Parent Class """
    def __init__(self):
        print("I am Parent class")

    def greet(self):
        print("Hello from parent class")
    
    def __str__(self):
        print("Thank You for calling parent class")


class Child(Parent):
    """ Child class who inherits parent class properties ."""
    def __init__(self):
        super().__init__()
        print("I am Child class")

    # Overridden Method
    def greet(self):
        print(" Hello from child class")
        
    def __str__(self):
        return "Thank You for calling child class"


# -------------------------------------------------------------------

def main() -> None:
    """ Main Function . """

    print("hello")
    child1 = Child()
    child1.greet()

    print("\nis child1 instance of Child class : ",isinstance(child1 , Child))
    print("is child1 instance of Parent class : ",isinstance(child1 , Parent))
    print("is child1 instance of object class : ",isinstance(child1 , object))
    print("is child1 instance of int class : ",isinstance(child1 , int))

    print(child1)


# -------------------------------------------------------------------

if __name__ == '__main__':
    main()