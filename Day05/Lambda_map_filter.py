from functools import reduce
import string

# -------------------------------------------------------------------
print("\n\n-------------------------------")
print("Demonstration of Lambda Function")


list_1 = [1,2,3,4,5,6]
print("Original List : ",list_1)

sqaure = lambda x : x**2
for l in list_1:
    print(sqaure(l) , end=" , ")

# -------------------------------------------------------------------

print("\n\n-------------------------------")
print("Demonstration of Map")

list_2 = list(map(sqaure,list_1))
print("Original List : ",list_1)
print("Mapped Squared list : ",list_2)

# -------------------------------------------------------------------
print("\n\n-------------------------------")
print("Demonstration of Lambda Function")

even_num = list(filter(lambda x: x%2==0 , list_2))
print("Original List : ",list_2)
print("Filtered Even List : ",even_num)

# -------------------------------------------------------------------
print("\n\n-------------------------------")
print("Demonstration of Reduce Function")

sum_of_all = reduce(lambda x,y : x+y , even_num)
print("Original List : ",even_num)
print("Sum of all with reduce is : ",sum_of_all)

# -------------------------------------------------------------------
print("\n\n-------------------------------")
print("Demonstration of Sorted Function")

unsorted_list = [5,85,61,1,45,36,52,48,61,2]
print("\nOriginal List : ",unsorted_list)
print("Sorted List : ",sorted(unsorted_list))


words = ["yash","nigam","brijraj", "gopal","arbaz","vinay","ravi"]
print("\nOriginal List : ",words)
print("Sorted List : ",sorted(words))

print("Sorted by length : ",sorted(words , key=len))