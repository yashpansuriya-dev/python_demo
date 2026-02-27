print("\n\n\n -------Login System ----------\n")

#List of Existing Users and their information
details = [ {'user':"yash123" , 'passw':"yashyash"}]


i_user = input("Enter username")

for detail in details:
    if detail['user'] == i_user: #It checks is user exists 
        p_user = input("Plase Enter your Password")
        if detail['passw'] == p_user: #Checks Password
            print("You are succesfully logged in")
        else:
            print("Wrong Passowrd")
    else:
        print("User doesn't exist")

