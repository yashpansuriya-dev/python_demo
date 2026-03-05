"""
Modules and Standard Library
 
import, from...import, math, random, datetime, os modules; create your own module.
 
Generate 10 random passwords, display formatted dates, list files in a directory
"""

# -------------------------------------------------------------------

import random
# Random Module

print("\nRandom between 0 to 1 : ",random.random())
print("Random Between 5 to 15 : ", random.randint(5,15))

names = ["yash", "brijraj", "gopal" , "nigam", "chauhan"]
print("\nThe Contestents are : ", names)
print("The lucky customer is : ",random.choice(names))


list_1 = [1,2,3,4,5,6,7,8,9]
print("\nOriginal List : ", list_1)

random.shuffle(list_1)
print("Shuffled  List : ", list_1)


random.shuffle(list_1)
print("Again Shuffled list List : ", list_1)

# -------------------------------------------------------------------

import math
from math import sqrt
# Math Module
print("-----------------------------------------------")


print("\nFactorial of 5 is : ",math.factorial(5))
print("Square root of 25 is : ",sqrt(25))

rad_90 = math.radians(90)
print("Sin(90) is : ",math.sin(rad_90))

print("\nFloor of 8.9 is : ",math.floor(8.9))
print("LCM of 5,15,25 is : ",math.lcm(5,15,25))

# -------------------------------------------------------------------
print("\n-----------------------------------------------")


from datetime import date
from datetime import time
from datetime import datetime

d = date.today()
print("Today date is ",d)

d= date(2026,5,27)
print("\nSetted date is : ",d)
print("Year is : ",d.year)
print("Date is : ",d.day)

t = time(13,26,57)
print("\nSetted time is ",t)
print("Hour is : ",t.hour)

current_time = datetime.now()
print("\nCurrent time is : ", current_time)

print("\n String Formatted time")
curr_time = datetime.now()

print("Date is DD-MM-YYYY is : ",curr_time.strftime("%d-%m-%Y"))
print("time is : ",curr_time.strftime("%H : %M : %S"))
print("Today is ",curr_time.strftime("%A"))
print("Clock time is : ",curr_time.strftime("%I : %M %p"))


# -------------------------------------------------------------------

import os

print("OS module\n")

cwd = os.getcwd()
print("Current Working directory is : ", cwd)

os.chdir(r'D:\intership_code\first\Day04')
print("New Working Directory : " , os.getcwd())
print("Files in this directory are : ",os.listdir())

os.chdir(r'..\Day05')
print("New Working Directory : " , os.getcwd())

try:
    os.mkdir('Day08')
except:
    print("Folder not created")
else:
    print("Folder created sucesfully")

os.rmdir('Day07')

# -------------------------------------------------------------------

import my_math_module
from my_math_module import multiply

print("\n Own Math Module")

print("Sum is : ",my_math_module.add(5,6))
print("Sqaure is : ",my_math_module.square(8))
print("Multiplication is : ",multiply(9,8))