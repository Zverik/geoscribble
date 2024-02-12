import os

# Set to localhost or a socket path.
PG_HOST = os.getenv('PGHOST', '/var/run/postgresql')

# Might want to use a proper user.
PG_USER = os.getenv('PGUSER', 'postgres')

# These are pretty much standard.
PG_PORT = os.getenv('PGPORT', '5432')
PG_DATABASE = os.getenv('PGDATABASE', 'postgres')

# Geoscribble-specific numbers
MAX_POINTS = int(os.getenv('MAX_POINTS', '100'))
MAX_LENGTH = int(os.getenv('MAX_LENGTH', '5000'))  # in meters
DEFAULT_AGE = int(os.getenv('DEFAULT_AGE', '182'))  # half a year

# For bbox requests
MAX_COORD_SPAN = float(os.getenv('MAX_COORD_SPAN', '0.3'))
MAX_IMAGE_WIDTH = int(os.getenv('MAX_IMAGE_WIDTH', '3000'))
MAX_IMAGE_HEIGHT = int(os.getenv('MAX_IMAGE_HEIGHT', '2000'))
