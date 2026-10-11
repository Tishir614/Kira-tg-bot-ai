class GroupNotFound(Exception):
    pass

class CharacterError(Exception):
    pass

class MarryMe(CharacterError):
    pass

class CharacterAlreadyMarried(CharacterError):
    pass

class UserNotHaveCharacter(CharacterError):
    pass

class SelfNotHaveCharacter(UserNotHaveCharacter):
    pass

class CharacterNotFound(CharacterError):
    pass

class MarryYourself(CharacterError):
    pass

class CharacterNotMarried(CharacterError):
    pass