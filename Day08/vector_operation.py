"""
    It has Class used for Vector and its operations , like
    sum , sub , scaling , magnitude , compare , ...
    With the use of Magic methods . 
"""
# -------------------------------------------------------------------

import math

# -------------------------------------------------------------------

class Vector:
    """
        Vector Class that represents cordinates and
        perform its operations.
    """
    Vector_dimension = 2

    def __init__(self , x , y):
        self.cord_x = x
        self.cord_y = y
    
    def __add__(self, other) -> tuple:
        return (self.cord_x + other.cord_x
            , self.cord_y + other.cord_y)
    
    def __sub__(self, other) -> tuple:
        return (self.cord_x - other.cord_x 
               , self.cord_y - other.cord_y)
    
    def __eq__(self, other):
        return (self.cord_x == other.cord_x 
                and self.cord_y == other.cord_y)
    
    def __str__(self):
        return f"x : {self.cord_x} , y:{self.cord_y}"

    def __repr__(self):
        return f"Vector(cord_x : {self.cord_x} , cord_y : {self.cord_y})"
     
    # Scaling Vector by K.
    def scaling_vector(self , k):
        self.cord_x = self.cord_x * k
        self.cord_y = self.cord_y * k
    
    def mag_vector(self):
        sum_ofsquare = (
            self.cord_x*self.cord_x
            + self.cord_y+self.cord_y
        )

        return math.sqrt(sum_ofsquare)
    
    # Getter and Setter of X
    @property
    def cord_x(self):
        return self._cord_x
    
    @cord_x.setter
    def cord_x(self , x):
        self._cord_x = x

    # Getter and Setter of Y
    @property
    def cord_y(self):
        return self._cord_y
    
    @cord_y.setter
    def cord_y(self , y):
        self._cord_y = y
    
# -------------------------------------------------------------------

def main() -> None:
    print("hello")

    vector_1 = Vector(2,7)
    vector_2 = Vector(-3,5)

    print("Vector 1 : ", vector_1)
    print("Vector 2 : ", vector_2)

    print("\nRepr format :: ")
    print("Vector 1 : ", repr(vector_1))
    print("Vector 2 : ", repr(vector_2))

    vector_3 = vector_1 + vector_2
    print("\nSum is : ", vector_3)

    vector_4 = vector_1 - vector_2
    print("\nSub is : ", vector_4)

    vector_1.scaling_vector(3)
    print("\nVector 1 scaled by 3 is : ", vector_1)

    print("\nMagnitude of vector 1 is : ", vector_1.mag_vector())

    print("\nvector1 == vector 2 : ", vector_1 == vector_2)

# -------------------------------------------------------------------

if __name__ == '__main__':
    main()

# -------------------------------------------------------------------
