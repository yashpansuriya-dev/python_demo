
# def fun_1(a):
#     a = 10
#     print("A in function : ",a)

# def fun_2(a):
#     global a = 10
#     print("A in function : ",a)


# a = 5
# print("A before function : ", a)
# fun_1(a)
# print("A after function : ", a)

# global b = 5
# print("\nB before function : ", a)
# fun_1(b)
# print("B after function : ", a)

# Global variable
x = 10


def show_value() -> None:
    """
    Demonstrates local and global variable scope.
    """
    x = 5  # Local variable (different from global x)
    print(f"Inside function (local x): {x}")


def show_global_value() -> None:
    """
    Accessing global variable inside function.
    """
    print(f"Inside function (global x): {x}")


def modify_global() -> None:
    """
    Modifies the global variable using 'global' keyword.
    """
    global x
    x = 20


def main() -> None:
    print(f"Before function call (global x): {x}")

    show_value()
    print(f"After show_value (global x): {x}")

    show_global_value()

    modify_global()
    print(f"After modify_global (global x): {x}")


if __name__ == "__main__":
    main()