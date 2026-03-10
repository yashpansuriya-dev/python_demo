"""
 If it looks like a duck and it quacks , 
 then it is a duck.
"""
# -------------------------------------------------------------------

class Animal:
    alive = True


class Dog(Animal):
    def speak(self):
        print("WOof !")


class Cat(Animal):
    def speak(self):
        print("MEOW !")


# Here,  car class has all required , methods and varribles so , it is
# Duck typed and become under Animal.
class Car:
    alive = False

    def speak(self):
        print("Honk!!")

# -------------------------------------------------------------------

def main() -> None:
    """ Main Function . """
    animals = [Dog(), Cat(), Car() ]

    for animal in animals:
        animal.speak()
        print(animal.alive)

# -------------------------------------------------------------------

if __name__ == '__main__':
    main()