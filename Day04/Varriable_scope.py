# -------------------------------------------------------------------

# Any varriable created inside function is local varrible 
# unless it has 'global'keyword . and it can be accessed only
# within function .

def my_function():
    x = 10  # Local variable 
    print("Inside function:", x)

my_function()
# print(x)  # Error  x is not defined outside the function

# -------------------------------------------------------------------

# any varrible created outside function is global varriable

y = 20  # Global variable

def my_function():
    print("Accessing global y:", y)  # Works fine

my_function()
print("Outside function:", y)

# -------------------------------------------------------------------


count = 0  # Global variable

def increment():
    global count  # Declare we want to use the global variable
    count += 1

increment()
print("Count after increment:", count)  # Output: 1

# -------------------------------------------------------------------


value = 100  # Global

def test():
    value = 50  # Local shadows global
    print("Inside function:", value)

test()
print("Outside function:", value)  # Global remains unchanged
