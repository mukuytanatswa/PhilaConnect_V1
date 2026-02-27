# Simple dictionary to keep track of users' states
user_state = {}

def set_state(phone, state):
    user_state[phone] = state

def get_state(phone):
    return user_state.get(phone)
