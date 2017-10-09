import numpy as np
from collections import defaultdict


class Logger:
    def __init__(self):
        self.logs = defaultdict(list)

    def add_log(self, name, value):
        self.logs[name].append(value)

    def log(self, header=None):
        ''' Write the mean of the values added to each key and clear previous values '''
        avg_dict = dict((key, '{:.4f}'.format(np.mean(value)))
                        for key, value in self.logs.items())
        self.logs = defaultdict(list)
        print_table(avg_dict, header)

def print_table(tags_and_values_dict, header=None, width=42):
    '''
    Print a pretty table =)
    Expects keys and values of dict to be a string
    '''

    tags_maxlen = max(len(tag) for tag in tags_and_values_dict)
    values_maxlen = max(len(value) for value in tags_and_values_dict.values())

    max_width = max(width, tags_maxlen + values_maxlen)

    print()
    if header:
        print(header)
    print((2 + max_width) * '-')
    for tag, value in tags_and_values_dict.items():
        num_spaces = 2 + values_maxlen - len(value)
        string_right = '{:{n}}{}'.format('|', value, n=num_spaces)
        num_spaces = 2 + max_width - len(tag) - len(string_right)
        print(''.join((tag, ' ' * num_spaces, string_right)))
    print((2 + max_width) * '-')
