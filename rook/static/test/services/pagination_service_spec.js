describe('pagination', function(){
  beforeEach(module('checkmate.services'));
  beforeEach(inject(function(pagination){
    this.pagination = pagination;
  }));

  describe('buildPaginator', function(){
    var offset,
        limit;
    beforeEach(function(){
      offset = undefined;
      limit = undefined;
    });

    it('should force offset to a number divisible by limit', function(){
      offset = 25;
      limit = 22;
      expect(this.pagination.buildPaginator(offset, limit).offset).toEqual(22);
    });

    it('should force offset to 0 if it is less than limit', function(){
      offset = 17;
      limit = 22;
      expect(this.pagination.buildPaginator(offset, limit).offset).toEqual(0);
    });

    it('should default limit 20 if no limit param found', function(){
      offset = undefined;
      limit = undefined;
      expect(this.pagination.buildPaginator(offset, limit).limit).toEqual(20);
    });

    it('should set offset to 0 if offset is null', function(){
      offset = null;
      limit = 20;
      expect(this.pagination.buildPaginator(offset, limit).offset).toEqual(0);
    });

    it('should default limit to 20 if limit cannot be parsed', function(){
      limit = 'ninja_turtles';
      expect(this.pagination.buildPaginator(offset, limit).limit).toEqual(20);
    });

    it('should ignore offset if offset cannot be parsed', function(){
      offset = 'cowabunga';
      limit = 14;
      expect(this.pagination.buildPaginator(offset, limit).offset).toEqual(0);
    });

    it('should round down if a user passes in a fraction for offset (default parseInt behavior)', function(){
      offset = 20.3;
      limit = 10;
      expect(this.pagination.buildPaginator(offset, limit).offset).toEqual(20);
    });

    it('should round down if a user passes in a fraction for limit (default parseInt behavior)', function(){
      limit = 14.9;
      expect(this.pagination.buildPaginator(offset, limit).limit).toEqual(14);
    });

    it('should set offset to 0 if the offset is negative', function(){
      offset = -2;
      limit = 2;
      expect(this.pagination.buildPaginator(offset, limit).offset).toEqual(0);
    });

    it('should default the limit to 20 if given limit is negative', function(){
      limit = -13;
      expect(this.pagination.buildPaginator(offset, limit).limit).toEqual(20);
    });

    it('should default the limit to 20 if limit is 0', function(){
      limit = 0;
      expect(this.pagination.buildPaginator(offset, limit).limit).toEqual(20);
    });

    it('should default the limit to 20 if limit is null', function(){
      limit = null;
      expect(this.pagination.buildPaginator(offset, limit).limit).toEqual(20);
    });

    it('should limit to 100 if limit if over 100', function() {
      limit = 1000000;
      expect(this.pagination.buildPaginator(offset, limit).limit).toEqual(100);
    });
  });

  describe('getPagingInformation', function(){
    var offset,
        limit,
        total_item_count,
        base_url;

    beforeEach(function(){
      offset = undefined;
      limit = undefined;
      base_url = "/deployments";
      total_item_count = 100;
    });

    it('should return current page if the limit and offset dont divide evenly', function(){
      limit = 2;
      offset = 3;
      expect(this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).currentPage).toEqual(2);
    });

    it('should return current page if limit and offset divide evenly', function(){
      limit = 2;
      offset = 4;
      expect(this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).currentPage).toEqual(3);
    });

    it('should return current page of 1 if there is no offset', function(){
      offset = null;
      expect(this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).currentPage).toEqual(1);
    });

    it('should return current page of 1 if offset is 0', function(){
      offset = 0;
      expect(this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).currentPage).toEqual(1);
    });

    it('should return current page of 1 when limit is greater than item count and there is an offset (modulo math forces offset to 0)', function(){
      limit = 200;
      offset = 50;
      total_item_count = 100;
      expect(this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).currentPage).toEqual(1);
    });

    it('should return current page of 1 if the total item count is 0', function(){
      offset = 20;
      limit = 10;
      total_item_count = 0;
      expect(this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).currentPage).toEqual(1);
    });

    it('should return the total number of pages', function(){
      limit = 3;
      total_item_count = 10;
      expect(this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).totalPages).toEqual(4);
    });

    describe('links', function(){
      var links;
      beforeEach(function(){
        links = {};
      });

      describe('with query params', function(){
        beforeEach(function(){
          base_url = '/deployments?status=UP';
        });
        it('should build the next link', function(){
          offset = 6;
          limit = 3;
          total_item_count = 10;
          links = this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).links;
          expect(links.next).toEqual({ uri: '/deployments?status=UP&limit=3&offset=9', text: 'Next' });
        });

        it('should build the previous link', function(){
          offset = 6;
          limit = 3;
          total_item_count = 10;
          links = this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).links;
          expect(links.previous).toEqual({ uri: '/deployments?status=UP&limit=3&offset=3', text: 'Previous' });
        });

        it('should build the numbered links', function(){
          offset = 6;
          limit = 3;
          total_item_count = 10;
          links = this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).links;
          expect(links.middle_numbered_links).toEqual([{ uri: '/deployments?status=UP&limit=3&offset=0', text: 1 }, { uri: '/deployments?status=UP&limit=3&offset=3', text: 2 }, { uri: '/deployments?status=UP&limit=3&offset=6', text: 3 }, { uri: '/deployments?status=UP&limit=3&offset=9', text: 4 }]);
        });
      });

      it('should build the next link', function(){
        offset = 6;
        limit = 3;
        total_item_count = 10;
        links = this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).links;
        expect(links.next).toEqual({ uri: '/deployments?limit=3&offset=9', text: 'Next' });
      });

      it('should build the previous link', function(){
        offset = 6;
        limit = 3;
        total_item_count = 10;
        links = this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).links;
        expect(links.previous).toEqual({ uri: '/deployments?limit=3&offset=3', text: 'Previous' });
      });

      it('should build the numbered links', function(){
        offset = 6;
        limit = 3;
        total_item_count = 10;
        links = this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).links;
        expect(links.middle_numbered_links).toEqual([{ uri: '/deployments?limit=3&offset=0', text: 1 }, { uri: '/deployments?limit=3&offset=3', text: 2 }, { uri: '/deployments?limit=3&offset=6', text: 3 }, { uri: '/deployments?limit=3&offset=9', text: 4 }]);
      });

      it('should not build previous link if there is only one page', function(){
        offset = 0;
        limit = 5;
        total_item_count = 3;
        links = this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).links;
        expect(links.previous).toBe(undefined);
      });

      it('should not build next link if there is only one page', function(){
        offset = 0;
        limit = 5;
        total_item_count = 3;
        links = this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).links;
        expect(links.next).toBe(undefined);
      });

      it('should not build previous link if there is only one page', function(){
        offset = 0;
        limit = 5;
        total_item_count = 3;
        links = this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).links;
        expect(links.previous).toBe(undefined);
      });

      it('should build previous link even if I am on the first page', function(){
        offset = 0;
        limit = 5;
        total_item_count = 10;
        links = this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).links;
        expect(links.previous).toBeDefined;
      });

      it('should build next link even if I am on the last page', function(){
        offset = 5;
        limit = 5;
        total_item_count = 10;
        links = this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).links;
        expect(links.next).toBeDefined;
      });

      it('should only build a max of 11 numbered links (first 3, middle 5, last 3)', function(){
        offset = 15;
        limit = 1;
        total_item_count = 30;
        links = this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).links;
        expect(links.first_numbered_links.length).toEqual(3);
        expect(links.middle_numbered_links.length).toEqual(5);
        expect(links.last_numbered_links.length).toEqual(3);
      });

      it('should build the first 3, middle 5, and last 3 links', function(){
        offset = 15;
        limit = 1;
        total_item_count = 30;
        links = this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).links;
        expected_first_uris = [
                                '/deployments?limit=1&offset=0',
                                '/deployments?limit=1&offset=1',
                                '/deployments?limit=1&offset=2'
                              ];
        expected_middle_uris = [
                                 '/deployments?limit=1&offset=13',
                                 '/deployments?limit=1&offset=14',
                                 '/deployments?limit=1&offset=15',
                                 '/deployments?limit=1&offset=16',
                                 '/deployments?limit=1&offset=17'
                               ];
        expected_last_uris = [
                               '/deployments?limit=1&offset=27',
                               '/deployments?limit=1&offset=28',
                               '/deployments?limit=1&offset=29'
                             ];
        expect(_.pluck(links.first_numbered_links, 'uri')).toEqual(expected_first_uris);
        expect(_.pluck(links.middle_numbered_links, 'uri')).toEqual(expected_middle_uris);
        expect(_.pluck(links.last_numbered_links, 'uri')).toEqual(expected_last_uris);
      });

      it('should not build duplicate numbered links from the front', function(){
        offset = 3;
        limit = 1;
        total_item_count = 30;
        links = this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).links;
        expected_first_uris = [
                                '/deployments?limit=1&offset=0'
                              ];
        expected_middle_uris = [
                                 '/deployments?limit=1&offset=1',
                                 '/deployments?limit=1&offset=2',
                                 '/deployments?limit=1&offset=3',
                                 '/deployments?limit=1&offset=4',
                                 '/deployments?limit=1&offset=5'
                               ];
        expected_last_uris = [
                               '/deployments?limit=1&offset=27',
                               '/deployments?limit=1&offset=28',
                               '/deployments?limit=1&offset=29'
                             ];
        expect(_.pluck(links.first_numbered_links, 'uri')).toEqual(expected_first_uris);
        expect(_.pluck(links.middle_numbered_links, 'uri')).toEqual(expected_middle_uris);
        expect(_.pluck(links.last_numbered_links, 'uri')).toEqual(expected_last_uris);
      });

      it('should not build duplicate numbered links from the end', function(){
        offset = 29;
        limit = 1;
        total_item_count = 30;
        links = this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).links;
        expected_first_uris = [
                                '/deployments?limit=1&offset=0',
                                '/deployments?limit=1&offset=1',
                                '/deployments?limit=1&offset=2'
                              ];
        expected_middle_uris = [
                                 '/deployments?limit=1&offset=27',
                                 '/deployments?limit=1&offset=28',
                                 '/deployments?limit=1&offset=29'
                               ];
        expected_last_uris = [];
        expect(_.pluck(links.first_numbered_links, 'uri')).toEqual(expected_first_uris);
        expect(_.pluck(links.middle_numbered_links, 'uri')).toEqual(expected_middle_uris);
        expect(_.pluck(links.last_numbered_links, 'uri')).toEqual(expected_last_uris);
      });

      it('should not build duplicate numbered links from the end with some overlap', function(){
        offset = 7;
        limit = 1;
        total_item_count = 13;
        links = this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).links;
        expected_first_uris = [
                                '/deployments?limit=1&offset=0',
                                '/deployments?limit=1&offset=1',
                                '/deployments?limit=1&offset=2'
                              ];
        expected_middle_uris = [
                                 '/deployments?limit=1&offset=5',
                                 '/deployments?limit=1&offset=6',
                                 '/deployments?limit=1&offset=7',
                                 '/deployments?limit=1&offset=8',
                                 '/deployments?limit=1&offset=9'
                               ];
        expected_last_uris = [
                               '/deployments?limit=1&offset=10',
                               '/deployments?limit=1&offset=11',
                               '/deployments?limit=1&offset=12'
                             ];
        expect(_.pluck(links.first_numbered_links, 'uri')).toEqual(expected_first_uris);
        expect(_.pluck(links.middle_numbered_links, 'uri')).toEqual(expected_middle_uris);
        expect(_.pluck(links.last_numbered_links, 'uri')).toEqual(expected_last_uris);
      });

      it('should not build negative numbered links', function(){
        offset = 0;
        limit = 1;
        total_item_count = 30;
        links = this.pagination.buildPaginator(offset, limit).getPagingInformation(total_item_count, base_url).links;
        expect(_.filter(links.numbered_links, function(link){return (link.text < 1); }).length).toEqual(0);
      });
    });
  });

  describe('#changed_params', function() {
    var offset,
        limit;
    beforeEach(function(){
      offset = undefined;
      limit = undefined;
    });

    it('should return false if no query params were passed', function() {
      expect(this.pagination.buildPaginator(offset, limit).changed_params()).toBeFalsy();
    });

    it('should return false if query params did not change', function() {
      limit = 10;
      offset = 10;
      expect(this.pagination.buildPaginator(offset, limit).changed_params()).toBeFalsy();
    });

    it('should return true if query params were changed because limit was not valid', function() {
      limit = -10;
      expect(this.pagination.buildPaginator(offset, limit).changed_params()).toBeTruthy();
    });

    it('should return true if query params were changed because offset was not valid', function() {
      offset = -10;
      expect(this.pagination.buildPaginator(offset, limit).changed_params()).toBeTruthy();
    });

    it('should return true if query params were changed because they were not valid', function() {
      limit = -10;
      offset = -10;
      expect(this.pagination.buildPaginator(offset, limit).changed_params()).toBeTruthy();
    });
  });
});
