describe('pagination', function(){
  beforeEach(module('checkmate.services'));
  beforeEach(inject(function(pagination){
    this.pagination = pagination;
  }));

  describe('extractPagingParams', function(){
    var query_params;
    beforeEach(function(){
      query_params = '';
    });

    it('should construct paging parameters from the query params', function(){
      query_params = { cheese: 'yes', offset: 25, limit: 22, baritone: false };
      expect(this.pagination.extractPagingParams(query_params)).toEqual('?offset=25&limit=22');
    });

    it('should return empty string if no paging params found', function(){
      query_params = { cheese: 'yes', baritone: false };
      expect(this.pagination.extractPagingParams(query_params)).toEqual('');
    });
  });

  describe('getPageInformation', function(){
    var offset,
        limit,
        total_item_count;

    beforeEach(function(){
      offset = 0;
      limit = 10;
      total_item_count = 100;
    });

    it('should return current page if the limit and offset dont divide evenly', function(){
      limit = 2;
      offset = 3;
      expect(this.pagination.getPagingInformation(offset, limit, total_item_count).currentPage).toEqual(2);
    });

    it('should return current page if limit and offset divide evenly', function(){
      limit = 2;
      offset = 4;
      expect(this.pagination.getPagingInformation(offset, limit, total_item_count).currentPage).toEqual(3);
    });

    it('should return current page of 1 if there is no offset', function(){
      offset = null;
      expect(this.pagination.getPagingInformation(offset, limit, total_item_count).currentPage).toEqual(1);
    });

    it('should return current page of 1 if offset is 0', function(){
      offset = 0;
      expect(this.pagination.getPagingInformation(offset, limit, total_item_count).currentPage).toEqual(1);
    });

    it('should return current page of 2 when limit is greater than item count and there is an offset', function(){
      limit = 200;
      offset = 50;
      total_item_count = 100;
      expect(this.pagination.getPagingInformation(offset, limit, total_item_count).currentPage).toEqual(2);
    });

    it('should default limit to 20 if limit cannot be parsed', function(){
      limit = 'ninja_turtles';
      offset = 50;
      total_item_count = 100;
      expect(this.pagination.getPagingInformation(offset, limit, total_item_count).currentPage).toEqual(3);
    });

    it('should default offset to 0 if offset cannot be parsed, setting current page to 1', function(){
      limit = 20;
      offset = 'cowabunga';
      total_item_count = 100;
      expect(this.pagination.getPagingInformation(offset, limit, total_item_count).currentPage).toEqual(1);
    });

    it('should round down if a user passes in a fraction for offset (default parseInt behavior)', function(){
      limit = 10;
      offset = 20.4;
      total_item_count = 100;
      expect(this.pagination.getPagingInformation(offset, limit, total_item_count).currentPage).toEqual(3);
    });

    it('should round down if a user passes in a fraction for limit (default parseInt behavior)', function(){
      limit = 25.6;
      offset = 77;
      total_item_count = 100;
      expect(this.pagination.getPagingInformation(offset, limit, total_item_count).currentPage).toEqual(4);
    });

    it('should return current page of 1 if the total item count is 0', function(){
      offset = 20;
      limit = 10;
      total_item_count = 0;
      expect(this.pagination.getPagingInformation(offset, limit, total_item_count).currentPage).toEqual(1);
    });

    it('should default the offset to 0 if the offset is negative, setting current page to 1', function(){
      limit = 20;
      offset = -1;
      total_item_count = 100;
      expect(this.pagination.getPagingInformation(offset, limit, total_item_count).currentPage).toEqual(1);
    });

    it('should default the offset to 0 if the offset is null, setting current page to 1', function(){
      limit = 20;
      offset = null;
      total_item_count = 100;
      expect(this.pagination.getPagingInformation(offset, limit, total_item_count).currentPage).toEqual(1);
    });

    it('should set currentPage to the last page if offset is greater than total item count', function(){
      limit = 20;
      offset = 500;
      total_item_count = 100;
      expect(this.pagination.getPagingInformation(offset, limit, total_item_count).currentPage).toEqual(5);
    });

    it('should return the total number of pages', function(){
      limit = 3;
      total_item_count = 10;
      expect(this.pagination.getPagingInformation(offset, limit, total_item_count).totalPages).toEqual(4);
    });

    it('should default the limit to 20 if given limit is negative', function(){
      limit = -1;
      offset = 0;
      total_item_count = 100;
      expect(this.pagination.getPagingInformation(offset, limit, total_item_count).totalPages).toEqual(5);
    });

    it('should default the limit to 20 if limit is 0', function(){
      limit = 0;
      offset = 0;
      total_item_count = 100;
      expect(this.pagination.getPagingInformation(offset, limit, total_item_count).totalPages).toEqual(5);
    });

    it('should default the limit to 20 if limit is null', function(){
      limit = null;
      offset = 0;
      total_item_count = 100;
      expect(this.pagination.getPagingInformation(offset, limit, total_item_count).totalPages).toEqual(5);
    });

    it('should set adjustedOffset to the offset which will return a #limit number of results', function(){
      limit = 20;
      offset = 500;
      total_item_count = 100;
      expect(this.pagination.getPagingInformation(offset, limit, total_item_count).adjustedOffset).toEqual(80);
    });
  });
});
