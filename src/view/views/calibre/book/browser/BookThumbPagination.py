
import wx
import logging.config
from src.view.constants import LOG_SETTINGS
from src.view.views.calibre.book.browser.BookThumbCrtl import ThumbnailCtrl, NativeImageHandler
import os
from src.view.views.calibre.book.browser.SearchBook import FindingBook
from src.view.util.FileOperationsUtil import FileOperations
from src.view.constants import ID_FIRST_RESULT, ID_LAST_RESULT, ID_PREVIOUS_RESULT, ID_NEXT_RESULT

logging.config.dictConfig(LOG_SETTINGS)
logger = logging.getLogger('extensive')
try:
    from agw import aui
    from agw.aui import aui_switcherdialog as ASD
except ImportError:  # if it's not there locally, try the wxPython lib.
    import wx.lib.agw.aui as aui
    from wx.lib.agw.aui import aui_switcherdialog as ASD


class ThumbnailCtrlPaginationPanel(wx.Panel):

    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        vBox = wx.BoxSizer(wx.VERTICAL)
        ####################################################################
        self.fileOperations = FileOperations()
        self.search = wx.SearchCtrl(self, size=(200, -1), style=wx.TE_PROCESS_ENTER)
        self.search.ShowSearchButton(1)
        self.search.ShowCancelButton(1)
        self.search.SetMenu(None)
        self.search.Bind(wx.EVT_TEXT_ENTER, self.OnSearch)
                
        self.thumbnailCtrl = ThumbnailCtrl(self, -1, imagehandler=NativeImageHandler)
#         findingBook = FindingBook(libraryPath=r'/docs/new/library')
#         books = findingBook.searchingBook(searchText='head')
        self.loadingBook()
        ####################################################################
        vBox.Add(self.search , 0, wx.EXPAND | wx.ALL)
        vBox.Add(self.thumbnailCtrl , 1, wx.EXPAND | wx.ALL)
        vBox.Add(self.constructTopToolBar() , 0, wx.EXPAND | wx.ALL)
#         vBox.Add(self.tree , 1, wx.EXPAND | wx.ALL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(vBox, 1, wx.EXPAND , 0)
        self.SetSizer(sizer)

    def OnSearch(self, event):
        logger.debug('onSearch')
        self.loadingBook()

    def loadingBook(self, searchText=None):
        libraryPath=r'/docs/new/library'
        if os.path.exists(libraryPath):
            findingBook = FindingBook(libraryPath=libraryPath)
            if searchText:
                books = findingBook.searchingBook(searchText=self.search.GetValue())
            else:
                findingBook.findAllBooks(pageSize=10)
            self.thumbnailCtrl.ShowBook(books)        

    def constructTopToolBar(self):

        # create some toolbars
        tb1 = aui.AuiToolBar(self, -1, wx.DefaultPosition, (10, 10), agwStyle=aui.AUI_TB_DEFAULT_STYLE | aui.AUI_TB_OVERFLOW)

#         tb1.SetToolBitmapSize(wx.Size(16, 16))
        # id, name, image, name, method, kind

        tools = [
            (ID_FIRST_RESULT, "First", "resultset_first.png", 'First', lambda e:self.onToolButtonClick(e), wx.ITEM_NORMAL),
            (ID_PREVIOUS_RESULT, "Previous", "resultset_previous.png", 'Previous', lambda e:self.onToolButtonClick(e), wx.ITEM_NORMAL),
            (ID_NEXT_RESULT, "Next", "resultset_next.png", 'Next', lambda e:self.onToolButtonClick(e), wx.ITEM_NORMAL),
            (ID_LAST_RESULT, "Last", "resultset_last.png", 'Last', lambda e:self.onToolButtonClick(e), wx.ITEM_CHECK),
            (),
#             (ID_REFRESH_ROW, "Result refresh", "resultset_refresh.png", 'Result refresh \tF5', self.onRefresh),
#             (ID_ADD_ROW, "Add a new row", "row_add.png", 'Add a new row', self.onAddRow),
#             (ID_DUPLICATE_ROW, "Duplicate selected row", "row_copy.png", 'Duplicate selected row', self.onDuplicateRow),
#             (ID_DELETE_ROW, "Delete selected row", "row_delete.png", 'Delete selected row', self.onDeleteRow),
            ]
        for tool in tools:
            if len(tool) == 0:
                tb1.AddSeparator()
            else:
                logger.debug(tool)
                toolItem = tb1.AddSimpleTool(tool[0], tool[1], self.fileOperations.getImageBitmap(imageName=tool[2]), kind=tool[5], short_help_string=tool[3])
                
                if tool[4]:
                    self.Bind(wx.EVT_MENU, tool[4], id=tool[0])
        pageNumber = [ "1", "2", "3" ]            
        choice = wx.Choice(tb1, 10, (-1, -1), (70, 25), pageNumber, style=0)
        choice.SetSelection(0)
        tb1.AddControl(choice)
        
        tb1.Realize()

        return tb1

    def onToolButtonClick(self, e):
        if e.Id == ID_FIRST_RESULT:
            logger.debug('ID_FIRST_RESULT')
        if e.Id == ID_PREVIOUS_RESULT:
            logger.debug('ID_PREVIOUS_RESULT')
        if e.Id == ID_NEXT_RESULT:
            logger.debug('ID_NEXT_RESULT')
        if e.Id == ID_LAST_RESULT:
            logger.debug('ID_LAST_RESULT')


if __name__ == '__main__':
    app = wx.App(False)
    frame = wx.Frame(None)
    try:
        panel = ThumbnailCtrlPaginationPanel(frame)
    except Exception as ex:
        logger.error(ex)
    frame.Show()
    app.MainLoop()
