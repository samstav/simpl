describe('pagination', function(){
  beforeEach(module('checkmate.services'));
  beforeEach(inject(function(pagination){
    this.pagination = pagination;
  }));

  describe('buildPagingParams', function(){
    var offset,
        limit;
    beforeEach(function(){
      offset = undefined;
      limit = undefined;
    });

    it('should force offset to a number divisible by limit', function(){
      offset = 25;
      limit = 22;
      expect(this.pagination.buildPaginator(offset, limit).buildPagingParams()).toEqual('?limit=22&offset=22');
    });

    it('should force offset to 0 if it is less than limit', function(){
      offset = 17;
      limit = 22;
      expect(this.pagination.buildPaginator(offset, limit).buildPagingParams()).toEqual('?limit=22&offset=0');
    });

    it('should construct paging parameters from the query params', function(){
      offset = 25;
      limit = 5;
      expect(this.pagination.buildPaginator(offset, limit).buildPagingParams()).toEqual('?limit=5&offset=25');
    });

    it('should default limit 20 if no limit param found', function(){
      offset = undefined;
      limit = undefined;
      expect(this.pagination.buildPaginator(offset, limit).buildPagingParams()).toEqual('?limit=20&offset=0');
    });

    it('should set offset to 0 if offset is null', function(){
      offset = null;
      limit = 20;
      expect(this.pagination.buildPaginator(offset, limit).buildPagingParams()).toEqual('?limit=20&offset=0');
    });

    it('should default limit to 20 if limit cannot be parsed', function(){
      limit = 'ninja_turtles';
      expect(this.pagination.buildPaginator(offset, limit).buildPagingParams()).toEqual('?limit=20&offset=0');
    });

    it('should ignore offset if offset cannot be parsed', function(){
      offset = 'cowabunga';
      limit = 14;
      expect(this.pagination.buildPaginator(offset, limit).buildPagingParams()).toEqual('?limit=14&offset=0');
    });

    it('should round down if a user passes in a fraction for offset (default parseInt behavior)', function(){
      offset = 20.3;
      limit = 10;
      expect(this.pagination.buildPaginator(offset, limit).buildPagingParams()).toEqual('?limit=10&offset=20');
    });

    it('should round down if a user passes in a fraction for limit (default parseInt behavior)', function(){
      limit = 14.9;
      expect(this.pagination.buildPaginator(offset, limit).buildPagingParams()).toEqual('?limit=14&offset=0');
    });

    it('should set offset to 0 if the offset is negative', function(){
      offset = -2;
      limit = 2;
      expect(this.pagination.buildPaginator(offset, limit).buildPagingParams()).toEqual('?limit=2&offset=0');
    });

    it('should default the limit to 20 if given limit is negative', function(){
      limit = -13;
      expect(this.pagination.buildPaginator(offset, limit).buildPagingParams()).toEqual('?limit=20&offset=0');
    });

    it('should default the limit to 20 if limit is 0', function(){
      limit = 0;
      expect(this.pagination.buildPaginator(offset, limit).buildPagingParams()).toEqual('?limit=20&offset=0');
    });

    it('should default the limit to 20 if limit is null', function(){
      limit = null;
      expect(this.pagination.buildPaginator(offset, limit).buildPagingParams()).toEqual('?limit=20&offset=0');
    });

  });

  describe('getPagingInformation', function(){
    beforeEach(function(){
      offset = undefined;
      limit = undefined;
      total_item_count = 100;
    });

    it('should return current page if the limit and offset dont divide evenly', function(){
      limit = 2;
      offset = 3;
      expect(this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count).currentPage).toEqual(2);
    });

    it('should return current page if limit and offset divide evenly', function(){
      limit = 2;
      offset = 4;
      expect(this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count).currentPage).toEqual(3);
    });

    it('should return current page of 1 if there is no offset', function(){
      offset = null;
      expect(this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count).currentPage).toEqual(1);
    });

    it('should return current page of 1 if offset is 0', function(){
      offset = 0;
      expect(this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count).currentPage).toEqual(1);
    });

    it('should return current page of 1 when limit is greater than item count and there is an offset (modulo math forces offset to 0)', function(){
      limit = 200;
      offset = 50;
      total_item_count = 100;
      expect(this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count).currentPage).toEqual(1);
    });

    it('should return current page of 1 if the total item count is 0', function(){
      offset = 20;
      limit = 10;
      total_item_count = 0;
      expect(this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count).currentPage).toEqual(1);
    });

    it('should return the total number of pages', function(){
      limit = 3;
      total_item_count = 10;
      expect(this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count).totalPages).toEqual(4);
    });
  });
});
