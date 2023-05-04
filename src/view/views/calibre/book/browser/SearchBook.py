import os
from src.dao.BookDao import CreateDatabase
from src.logic.BookShellOperation import BookTerminal


class FindingBook():
    '''
    This class searches book detail in Opal database.this database would be created in workspace(Opal library).
    '''

    def __init__(self, libraryPath=None):
        self.libraryPath = libraryPath
        self.createDatabase = CreateDatabase(libraryPath=libraryPath)

    def searchingBook(self, searchText=None, exactSearchFlag=False, pageSize=10, offset=0):
        '''
        This method return list of books matching with search text.
        @param searchText: may be a book name 
        '''
        books = []
        if searchText is None or searchText == '':
            books, count = self.findAllBooks()
        else:
            os.chdir(self.libraryPath)
            books, count = (
                self.createDatabase.findByBookName(searchText)
                if exactSearchFlag
                else self.createDatabase.findBySimlarBookName(
                    bookName=searchText, limit=pageSize, offset=0
                )
            )
        return books, count 
    
    def countAllBooks(self):
        return self.createDatabase.countAllBooks()

    def findBookByNextMaxId(self, bookId=None):
        return self.createDatabase.findBookByNextMaxId(bookId)

    def findBookByPreviousMaxId(self, bookId=None):
        return self.createDatabase.findBookByPreviousMaxId(bookId)
    
    def findAllBooks(self, pageSize=None, offset=0):
        '''
        This method will give all the books list in book library.
        '''
        books = []
        os.chdir(self.libraryPath)
        books, count = self.createDatabase.findAllBook(pageSize=pageSize, offset=offset)
        return books, count

    def findBookByIsbn(self, isbn_13):
        return self.createDatabase.findBookByIsbn(isbn_13)

    def getMaxBookId(self):
        os.chdir(self.libraryPath)
    
    def deleteBook(self, book):
        '''
        removing book from database and files.
        @param book: book object 
        '''
        bookPath = book.bookPath
        if isSuccessfulDatabaseDelete := self.createDatabase.removeBook(book):
            BookTerminal().removeBook(bookPath=bookPath)
            
    def findFolderWithoutBook(self):
        '''
        this method will find all the folder without book.
        '''
        directory_name = self.libraryPath
        os.chdir(directory_name)
        listOfDir = [ name for name in os.listdir(directory_name) if os.path.isdir(os.path.join(directory_name, name)) ]
        if listOfDir:
            listOfDir.sort(key=int)
        defaulterList = []
        for dir in listOfDir:
            levelOne = os.path.join(directory_name, dir)
            lst = [
                sName.split('.')[-1:][0]
                for sName in os.listdir(levelOne)
                if os.path.isfile(os.path.join(levelOne, sName))
            ]
#             if 'pdf' not in lst:
#                 defaulterList.append(levelOne)
            if len(lst) < 3:
                defaulterList.append(levelOne)


#         print defaulterList
if __name__ == '__main__':
#     print 'hi'
    findingBook = FindingBook()
    findingBook.findFolderWithoutBook()
