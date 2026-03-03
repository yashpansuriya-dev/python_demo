'''
 A student app , which has Functionality of 
    Add -> add new student 
    Delete -> delete student by name
    Search -> search student by name
    List -> List all student details
    Highest Marks -> fetch student with highest marks
    
'''
# ----------------------------------------------------------------------

import string

# ---------------------------------------------------------------------

# All Functions of student - add , delete , list , search


# Add student function
def student_add(roll_no : int , name: string, 
                marks: int, stu_record: list) -> list:
    """
        It takes roll no. , name and marks of student, and
        add it in student list .

        Args :
            roll_no (int) : roll no. of student
            name (string) : Name of student
            marks (int) : Student's overall marks
            stu_record (list) : list containing all students data.

        Returns :
            list : returns list containing all stu_record .

    """

    stu_record.append({'roll_no': roll_no, 'name': name,
                       'marks': marks})


# Searching student
def student_search(name: string, stu_record: list) -> dict|None:
    """
        It Serch the student by their name
        and print its info .

        Args :
            name (string) : Name of student

        Returns :
            stu_record (list) : list containing all students data.
    """
    print("Here is detail of ", name)
    

    for c in stu_record:
        # Iterates through all student record 
        # and print who matches name

        if c['name'] == name:
            print(f"\n Roll no. : {c['roll_no']} ,\
                        Name : {c['name']},\
                        Marks : {c['marks']}")
            return c
        else:
            pass

    print("Oops ! Name not found")
    return None


# List student
def student_list(stu_record: list) -> None:
    """
        It prints all the info of students,
        roll no. , name and marks.

        Args :
            stu_record (list) : list containing all student details.

        Returns :
            None : It just prints .
    """
    print("Here are Details of Students : ")

    print("-----------------------------------------------------")
    print("\n| Roll no      |       Name      |       Marks    |")

    for c in stu_record:
        # Prints every record
        print(f"\n|      {c['roll_no']}      |       {c['name']}      |       {c['marks']}    |")
    
    print("-----------------------------------------------------")

        
# Deleting student
def student_del(name: string, stu_record: list) -> dict|None:
    """
        It delete the record of student
        by its name .

        Args :
            name (string) : name of student thst needs to be deleted.
            stu_record (list) : list containing all students details.

        Returns :
            dict : deleted student details .
    """
    del_student = student_search(name, stu_record)
    if(del_student is None):
        print("Student does't exist")
        return None
    else:
        stu_record.remove(del_student)  # remove the dict student
        return del_student
    
def highest_marks(stu_record : list) -> dict:
    highest_mark_student = {}
    max_marks = 0

    for student in stu_record:
        if student['marks'] > max_marks:
            max_marks = student['marks']
            highest_mark_student = student
    
    print(f"The Highest mark student is {highest_mark_student['name']}")
    return highest_mark_student


            


# ---------------------------------------------------------------------

def main() -> None:
    stu_record = []
    c = 1
    while (c != 0):
        print("\nWelcome to Student Record System")
        print("Press 0 : exit")
        print("Press 1 : List All Students")
        print("Press 2 : Add Student")
        print("Press 3 : Search Student")
        print("Press 4 : Delete Student")
        print("Press 5 : Fetch Student with Highest Mark")

        c = int(input("Enter Your Choice : "))

        if c == 0:
            print("Thank You , for using student record System .")
            break
        elif c == 1:
            student_list(stu_record)

        elif c == 2:
            rollno = int(input("Please Enter your Roll no. : "))
            name = input("Please Enter your name : ")
            marks = int(input("Please Enter your Marks : "))
            student_add(rollno, name, marks, stu_record)

        elif c == 3:
            name = input("Please Enter your name : ")
            student_search(name, stu_record)

        elif c == 4:
            name = input("Please Enter your name : ")
            student_del(name, stu_record)

        elif c == 5:
            highest_marks(stu_record)


# ---------------------------------------------------------------------


if __name__ == "__main__":
    main()
