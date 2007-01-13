__version__ = "0.8.1"

from hachoir_metadata.metadata import extractMetadata

# Just import the module,
# each module use registerExtractor() method
import hachoir_metadata.image
import hachoir_metadata.audio
import hachoir_metadata.video
import hachoir_metadata.archive
import hachoir_metadata.jpeg
import hachoir_metadata.riff
