"""
Create an Animal base class, then Dog and Cat subclasses
with overridden speak()
"""
# -------------------------------------------------------------------

class Animal:
    """ Base class : Animal """
    alive = True

    def speak(self):
        print("Animal speaks")
    
    def __str__(self):
        print("I am Animal")

class Dog(Animal):
    """ Derived from Animal : Dog"""
    def speak(self):
        print("It bowsss") 
    
    def __str__(self):
        print("I am Dog")

class Cat(Animal):
    """ Derived from Animal : Cat """
    def speak(self):
        print("It mewosss")
            
    def __str__(self):
        print("I am Cat")

# -------------------------------------------------------------------

def main() -> None:
    """ Main Function . """
    print("hello")

    dog_1 = Dog()
    dog_1.speak()

    cat_1 = Cat()
    cat_1.speak()
    cat_1.printa()

    print(dog_1)
    print(cat_1)

# -------------------------------------------------------------------

if __name__ == "__main__":
    main()