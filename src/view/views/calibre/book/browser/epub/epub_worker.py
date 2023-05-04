import Image
from bs4 import BeautifulSoup as BS
from bs4 import Tag
import cStringIO
from zipfile import ZipFile as ZP


class EpubWorker():
    def open_epub(self, in_file):
        return ZP(in_file)
    
    def get_epub_content_soup(self, _ePub):
        try:
            the_container = _ePub.read('META-INF/container.xml')
        except AttributeError as e:
            print(f'Error encountered: {e}')
            return

        cSoup = BS(the_container)
        rootfile = cSoup.find('rootfile')

        try:
            the_content = rootfile.attrs['full-path']
        except KeyError as e:
            print(f'Error encountered: Key {e} does not exist!')
            return

        try:
            mSoup = BS(_ePub.read(the_content))
        except:
        # All encompassing except, this will be changed.
            raise

        return mSoup
    
    def get_epub_general_info(self, content_soup):
        meta_info = {}

        for s in ['title', 'language', 'creator', 'date', 'identifier',
                  'publisher', 'source', 'description']:
            try:
                meta_info[s] = content_soup.findAll(f'dc:{s}')[0].text
            except IndexError:
                meta_info[s] = content_soup.find(f'dc:{s}')
        return meta_info
    
    def get_epub_content_lists(self, content_soup):
        img_list = []
        text_list = []
        css_list = []
        spine_list = [
            item.attrs['idref'] for item in content_soup.spine.findAll('itemref')
        ]
        the_manifest = content_soup.manifest.findAll('item')

        for item_id in spine_list:
            text_list.extend(
                item.attrs['href']
                for item in the_manifest
                if item_id == item.attrs['id']
                and item.attrs['media-type'].startswith('application')
            )
        for item in the_manifest:
            if item.attrs['media-type'].endswith('css', -3):
                css_list.append(item.attrs['href'])
            if item.attrs['media-type'].startswith('image'):
                img_list.append(item.attrs['href'])

        return img_list, text_list, css_list
    
    def get_epub_section(self, _ePub, section):
        try:
            return BS(_ePub.read(section))
        except KeyError:
            for item in _ePub.namelist():
                if section in item:
                    return BS(_ePub.read(item))
        except:
            print('Received an error from the "get_epub_section" function.')
            return
    
    def preprocess_image(self, _ePub, image):
        try:
            _image = _ePub.read(image)
        except KeyError:
            for item in _ePub.namelist():
                if image in item:
                    _image = _ePub.read(item)
        imgData = cStringIO.StringIO(_image)
        return Image.open(imgData)
    
    def clean_convert_links(self, in_page):

        '''Adjust internal links so that the point to memory instead
        of the ePub file. We start with images.'''
        orig_link = None
        pSoup = in_page
        for image in pSoup.findAll('img'):
            new_link = image.attrs['src'].strip('../')
            image.attrs['src'] = f'memory:{new_link}'

        for image in pSoup.findAll('image'):
            try:
                image_link = image.attrs['xlink:href']
                src_tag = Tag(pSoup, name='img')
                src_tag.attrs['src'] = f'memory:{image_link}'
                image.replaceWith(src_tag)
            except:
                raise
        # Conversions for other types of links will be added at a later time.
        # This is to help ensure we don't convert the wrong links.
        return pSoup.prettify('latin-1')
    
