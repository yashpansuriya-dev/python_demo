"""
Challenge
 
Count word frequency in a paragraph using a dictionary.

"""

# ---------------------------------------------------------

import string

# ---------------------------------------------------------

def count_words(para : string) -> dict:
    """
     It returns a Dictinary which has word and 
     its frequency from paragraph , in key-value
     pair .

     Args:
        para (string): Paragraph or string 

    Returns:
        dict: it contains word : frequency in 
              key - value pair.

    """
    word_freq = {}

    for word in para.upper() :
        # If word exists in dict. it updates by 1 and
        #  if don't exist then default 0 .
        if word not in [' ' , ',', '.']:
            word_freq[word] = word_freq.get(word, 0)+1
    
    return word_freq

# ------------------------------------------------------------------

def main() -> None :
    para = "Daskroi is situated within Ahmedabad district in the " \
       "state of Gujarat, western India. It functions as a taluka, " \
       "comprising several villages and towns and serving as a local " \
       "administrative unit. The region lies relatively close to " \
       "Ahmedabad city, providing access to urban infrastructure," \
       " markets, and transport networks"

    # para = "yaaaaasshhhhhhhh"

    word_freq = count_words(para)
    print(word_freq)

# ------------------------------------------------------------------

if __name__ == "__main__":
    main()