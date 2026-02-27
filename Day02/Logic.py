""" 
 Here , I explored all logical operators , boolean logic along with for and while loop , 
 and some keywords like Pass,Continue, break.
"""


#Student Marks Checks with if-else Logic
marks = 50

if marks<33:
    print("Student fail")
elif marks>=33 and marks<70:
    print("Second distinction")
elif marks>=70 and marks<=100:
    print("First distinction")


#Lottery win 
ticket_no = 5246
winners = [1203,5246,4128,6324,2565,1456,8651]

if ticket_no in winners:
    print("Hurray ! you win the lottery")
elif ticket_no == 0000:
    print("Hurray ! , you won 1 crores")
else:
    print("Sorry , Better luck next time")


#Boolean Logic Check
a=123
b = None

if a:
    print("A")
if b:
    print("B")

a = True
b= False

print(a or b)
print(a and b)
print(not a)

#Nested Loop and Conditions to find biggest number out of three
a=52
b=41
c=78

if a>b:
    if a>c:
        print("A is bigger") #here, if a is bigger then b and c then A is biggest
    else:
        print("C is bigger") #if a>b but , c is bigger then a ,then C is biggest
else:
    if b>c:
        print("B is bigger")
    else:
        print("C is bigger")


# Grade Calculator
marks = int(input("ENter your marks : "))
print("Your grade is" , end=" ")
if marks<33:
    print("F")
elif marks >=33 and marks <70:
    print("D")
elif marks >=70 and marks<80:
    print("C")
elif marks >= 80 and marks<90:
    print("B")
elif marks >=90 and marks <=100:
    print("A")
else:
    print("Invalid marks")


#Loops and enumerate and iterator , pass,continue ,break 
for i in range(10):
    print(i)

j=1
while j<5:
    print(j)
    j = j+1

fruits = ["apple","banana","grape", "mango"]

# print(enumerate(fruits))
print(list(enumerate(fruits)))

for i,fruit in enumerate(fruits):
    print(f"at index {i} is {fruit}")

for i in iter(fruits):
    print(i)

for i in range(10):
    if i == 6:
        break
    print(i)

for i in range(10):
    if i == 6:
        continue
    print(i)

for i in range(10): #indentation error
    continue




