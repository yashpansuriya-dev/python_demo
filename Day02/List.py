""" 
    Here , I learned List and its various methods Along with List comprehension and Filtering.

    append() -> at element at last
    pop() -> remove element by index by default last index
    remove() -> remove element by value
    extend() -> it concates list with any other list,set,tuple,or other data .
    insert() -> insert element at specified index 
    count() -> count occurence of element
    index() -> return index of given element at first occurence
    sort() -> sort list with modifying original list

    List comprehension : 
        list1 = [x*x for x in l1 if x%2 == 0]
                  |       |          |
                output   loop      condition(if any)

    List Slicing : 
       list[ 2 : 8 :  3 ]
             |   |    |
           start stop step

           (stop is not included)
    
"""

import random

list1 = [2,5,6]
list2 = [2,5,7,4,6,2,2,9]

# Appending value at end of list
print("\nBefore Appending",list2)
list2.append(10)
print("After Appending",list2)

# Inserting Value at specified Index
list2.insert(1,25)
print("\nAfter Inserting element at index 1",list2)

# Counting Occurence of element
print("\nno. of occurence of 2 is : ",list2.count(2))

# Extending or concating list
print("\nAfter Extending List2 with List1 ")
list2.extend(list1)
print(list2)

# Finding index of Element
print("\n element 9 is at index : ",end="")
print(list2.index(9))


list2.pop() # Remove element by index
print("\nAfter popped last element with index",list2)


list2.remove(2) # It removes by value
print("\nAfter removing element 2  with value",list2)


print("\nSorting List ")
list2.sort() # Sorts list
print(list2)

print("\nSquared List with comprehension")
nums = [1,2,3,4,5,6,7,8,9,10] 
nums_sq =[ x*x for x in nums] # List comprehension
print(nums_sq)

# List Slicing
print("\nList Slicing for " , nums)
print("2:8 -- ",nums[2:8])
print("0 to 11 with step 2 --",nums[0:11:2])
print("all element with step 2 --",nums[::2])
print("Reverse list -- ",nums[::-1])

nums[2] = 88
print(nums)
nums[2] = 3

# Even numbers with List filtering
even_nums = [x for x in nums if x%2 == 0]
print("\nEven numbers with list filtering",even_nums)


print("\nmaximum value of list : ")
# find the max without Max()

l1 = [3,6,44,96,43,2,67,3,22,68]
l1.sort()
print(l1[-1]) # 1st method

# 2nd Method
largest = 0
for x in l1:
    if largest<x:
        largest = x
print(largest)

#Squred List with List Comprehension
def squared_list_genrator(a : int , b : int) -> list :
    """ 
        It generates a List of squared numbers with
        given range , and returns it.

        Args :
            a (int) : Starting value of list
            b (int) : Ending value of list

        Returns : 
            List : a List object containing sqaured numbers of 
                    given range
    """
    return [x*x for x in range(a,b)]

print(squared_list_genrator(5,10))


# Highest Marks of Student
student_marks = list(random.sample(range(1,100),20))
print("\n\nList of Marks of Students: ",student_marks)


def highest_marks(student_marks : list , k : int ) -> None :
    """ 
     It Gives Top K Students with Highest marks , and uses
      Sort funcion .

      Args : 
        student_marks (List) : List containing marks of students.
        k (int) : desired no. of students with highest marks.

      Returns :
        None : It prints K  Students with highest marks


    """
    print(f"\nThe first {k} Students with Highest Marks are : ",end=" ")
    student_marks.sort(reverse=True) # It sorts marks in descending order

    # Loop Iterate K time and Pops value
    for i in range(k):
        print(student_marks[i]," ,  ",end="") 

highest_marks(student_marks , 3)