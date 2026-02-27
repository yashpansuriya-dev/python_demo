#task - 1 - basic setup
print("Task-1\n\n")
from datetime import datetime
import time

name = "Yash Pansuriya"
age = 21

print(f"my name is {name}")
print(f"i am {age} years old")
print(datetime.now())

print("\n\n\n Task-2\n")
#task 2 - dynamic type 
a =5
print(type(a))

a="yash pansuriya"
print(type(a))

a=8.5
print(type(a))

b=None
print(type(b))

a=True
print(type(a))

name="Yash Pansuriya"
cgpa = 8.6
passing = True
marks = 81

print(f"hi , my name is {name} , and i am doing my final year from vgec college and i got {marks} in last semester , so my overall cgpa is {cgpa} , so i am {"passed" if passing else "failed"} ")

# Task 3 - Strings
print("\n\n\nTask-3\n")
name = "Yash Pansuriya"
print(name.lower())
print(name.upper())
print(name.capitalize())


print(name[2:7])
print(name[::-1])
print(name[-5:-2])
print(name[-2:-5:-1])


txt = "  Hello World "
print(txt.strip())


names = name.split(" ")
for n in names:
    print(n)

newname = name.replace('a','x')    
print(newname)

#first occurence of word find
text = "i joined in Techforce Global as a python intern"
print("the first occurence of letter e is ", text.find('e'))

#count vowels
# vowel = ['a','e','i','o','u','A','E','I','O','U']
vowel = "aeiouAEIOU"
count=0
for n in "Yasheoh":
   if n in vowel:
       count = count+1

print("vowels in text are :",count)

#greeting and f-string
fullname = "Yash Pravinbhai Pansuriya"
f_name = fullname.split(" ")[0]
m_name = fullname.split(" ")[1]
l_name = fullname.split(" ")[2]
print(f"full name is , {l_name} {f_name} {m_name}")
print(f"hello ! , {f_name} {l_name}")


#time with fstring
ctime = time.ctime()
times = ctime.split(" ")
print(f"Todays is {times[2]} {times[1]} and {times[0]} and year is {times[4]} ")

t = times[3].split(":")
print(f"currently hour is {t[0]} , minute is {t[1]} , and second is {t[2]}")

