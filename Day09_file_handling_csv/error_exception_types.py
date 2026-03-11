"""
    Errors :- at compile time 
        SyntaxError :- common error 

    Exception :- at run time
        ZeroDivisionError
        ValueError  :- int("yash")
        IndexError :- data[5]
        NameError :- varrible not existed
        IndetationError :- when not proper indetation
        KeyError :- key not existed
        TypeError :- print("yash"+5) , function and operation 
                            are applied in an incorrect type.
        ImportError :- imported module is not found.
        MemoryError :-when a program runs out of memory.
        AttributeError:- attribute assignment is failed.

"""
# -------------------------------------------------------------------

def main() -> None:
    print("hello")

    # ERRORS :-
    # SyntaxError - ( never closed
    # print("yash"


    # EXCEPTIONS :-
    # Zero Division Error
    # res = 10/0 

    # NameError : -> res is not defined
    # print(res[1]) - 

    # IndexError : list index out of range
    # data = [0,1]
    # print(data[2]) -> 

    # SyntaxError -expected :
    # for i in range(10) -
    #   print(i)

    # IndentationError 
    # for i in range(10):
    # print(i) :- 

    # ValueError  - Invalid literal for int()
    # print(int("yash"))

    #Key error
    # dict_1 = {"name": "yash"}
    # print(dict_1['age'])

    # TypeError: 'tuple' object does not support item assignment
    # my_tuple = (1,2)
    # my_tuple[0] = 5

    # TypeError 
    # print("yash"+25)

    # MemoryError
    # while(True):
    #     print("Hello")

    # AttributeError: 'list' object has no attribute 'myfunction'
    # mylist = [1,2]
    # mylist.myfunction(5)

# -------------------------------------------------------------------

if __name__ == '__main__':
    main()