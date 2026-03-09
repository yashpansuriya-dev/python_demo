"""
Classes and Objects
 
class keyword, __init__, self, instance vs class attributes, instance methods
 
Create a Car class with attributes make, model, year and methods accelerate, brake
"""

# -------------------------------------------------------------------

class Car:
    """
    A car class which has all info of car.
    """
    curr_speed = 0

    def __init__(self, company: str, model: str, year: int):
        self.company = company
        self.model = model
        self.year = year
    
    def accelerate(self):
        self.curr_speed = self.curr_speed+10
        print(f"It accelerates to {self.curr_speed}")
    
    def brake(self):
        self.curr_speed = self.curr_speed-10
        print(f"speed reduced to {self.curr_speed}") 
    
    def print_details(self):
        print(f"This car is {self.company} {self.model} , {self.year} model \
and current speed is {self.curr_speed}")


class Animal:
    """
    Animal class which has attributes name, color
    and methods eat.
    """
    eats = "food"

    def __init__(self, name, color):
        self.name = name
        self.color = color
    
    def __str__(self):
        return f"this is {self.name} and it has {self.color} colour."

    def eat(self):
        print(f"it eats {self.eats}")

class Watery_animal(Animal):
        def __init__(self, name, color):
            self.name = name
            self.color = color

# -------------------------------------------------------------------


def main() -> None:
    """ Main Function . """
    print("Hello")

    print("----------------- Car -------------")

    my_car = Car("Honda", "Amaze", "2024")
    my_car.accelerate()
    my_car.accelerate()
    my_car.brake()
    my_car.accelerate()
    my_car.print_details()


    print("----------------- Animal -------------")
    animal1 = Animal("dog", "black")
    animal1.eats = 'meat'
    animal1.eat()
    print(animal1)

    octopus = Watery_animal("octopus", "red")
    octopus.eats = "Meeeeat"
    print(octopus)

# -------------------------------------------------------------------

if __name__ == "__main__":
    main()