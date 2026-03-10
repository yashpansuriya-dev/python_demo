"""
OOP Advanced
 
__str__, __repr__, __len__, __eq__; @property decorator; @staticmethod; @classmethod
Add __str__ to all previous classes; use @property for input validation.
"""

# -------------------------------------------------------------------

from datetime import datetime

# -------------------------------------------------------------------

class CarCompany:
    def __init__(self, year ,  cars):
        self.cars = cars
        self.year = year
    
    # len(object)
    def __len__(self):
        return len(self.cars)
    
    # print(object) or str(object)
    def __str__(self):
        return (
            f"this company is established on {self.year} ," 
            f"Car's List : {self.cars}")
    
    # repr(str) -> Representative string
    def __repr__(self):
        return f"CarCompany(year={self.year}, cars : {self.cars}"
    
    # ==
    def __eq__(self, other):
        return self.cars == other.cars and self.year == other.year

    # Getter
    @property
    def year(self):
        return self._year

    # Setter
    @year.setter
    def year(self, value):
        if value < 1800 or value > 2700:
            raise ValueError("Enter Valid Year")
        self._year = value
    
    
    # No need to use self
    @staticmethod
    def vision():
        print("Delivering Best Cars")


    # takes class itself as first arg.
    # Bound to class rather than instance of class(Object)
    @classmethod
    def duration_years(cls, year):
        return (datetime.now().year - year)

# -------------------------------------------------------------------

def main() -> None:
    """ Main Function . """
    print("Hello")

    honda_1 = CarCompany(1985, ['amaze', 'city', 'shine', 'elevate', 'civic'])
    honda_2 = CarCompany(1985, ['amaze', 'city', 'shine', 'elevate', 'civic'])

    tata = CarCompany(2002, ['nano', 'altroz', 'nexon', 'tiago', 'harrier'])

    print("\Tata Motors")
    print("Length of tata is : ",len(tata))
    print("String of tata : ",str(tata))
    print("repr of tata : ",repr(tata))

    # Setting year with property
    tata.year = 2006
    print("company estiblished from",tata.duration_years(tata.year) , "years")
    
    print("Company Vision : ",tata.vision())

    print("\n\n")
    print("Honda1 == honda2 : " ,honda_1 == honda_2)
    print("honda1 == tata : ",honda_1 == tata)

# -------------------------------------------------------------------

if __name__ == "__main__":
    main()