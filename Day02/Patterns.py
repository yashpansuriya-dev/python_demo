"""
    It is Program for All the different patterns logic ,

    I builded Strong Loop logic through this various Patterns
"""

n =5 #lines for pattern

print("\n\nPattern 1")
for i in range(1,n+1):
    for j in range(1,i+1):
        print("*",end="")
    print("")

#Another way for Pattern-1
for i in range(1,6):
    print("*" * i)


print("\n\nPattern 2")
for i in range(1,n+1):
    for j in range(1,n+1-i):
        print(" ",end="")
    for j in range(1,i+1):
        print("*",end="")
    print("")


print("\n\nPattern 3")
for i in range(n,0,-1):
    for j in range(1,i+1):
        print("*",end="")
    print("")


print("\n\nPattern 4")
for i in range(1,n+1):
    for j in range(1,i+1):
        print(j," ",end="")
    print("")


print("\n\nPattern 5")
k=1
for i in range(1,n+1):
    for j in range(1,i+1):
        print(k," ",end="")
        k=k+1
    print("")


print("\n\nButterfly Pattern")
for i in range(1,n+1):
    for j in range(1,i+1):
        print("*",end="")
    for j in range(1,(2*(n-i)+1)):
        print(" ",end="")
    for j in range(1,i+1):
        print("*",end="")
    print("")
for i in range(n,0,-1):
    for j in range(1,i+1):
        print("*",end="")
    for j in range(1,(2*(n-i)+1)):
        print(" ",end="")
    for j in range(1,i+1):
        print("*",end="")
    print("")


print("\n\nwhole square")
for i in range(1,n+1):
    for j in range(1,n+1):
        print("*",end="")
    print("")


print("\n\nhollow square")
for i in range(1,n+1):
    for j in range(1,n+1):
        print("*",end="") if i in [1,n] or j in [1,n] else print(" ",end="")
    print("")


print("\n\nK pattern")
for i in range(n,0,-1):
    for j in range(1,i+1):
        print("*",end="")
    print()
for i in range(1,n+1):
    for j in range(1,i+1):
        print("*",end="")
    print()


print("\n\nDiamond pattern")
for i in range(1,n+1):
    for j in range(1,n-i+1):
        print(" ",end="")
    for j in range(1,2*i):
        print("*",end="")
    print()
for i in range(n,0,-1):
    for j in range(1,n-i+1):
        print(" ",end="")
    for j in range(1,2*i):
        print("*",end="")
    print()


#Table from 1 to 10
for i in range(1,11):
    print("Table of",i)
    for j in range(1,11):
        print(f"{i} X {j} = {i*j}")
    print("\n")

    
#find all prime numbers for given range
for i in range(2,51):
    is_prime=True #flag for check prime number
    for j in range(2,i):
        if(i % j == 0):
            flag=False #if number gives remainder 0 ,that means it is not prime number
            break
    if is_prime:
        print(i,end="  ")
