class CalcApp

  constructor: ->

    # Set up our initial collection and view.
    Items = new ItemCollection

    App = new AppView
      el: '#racker-calculator'
      collection: Items


  # Pricing hash
  Pricing =
    linux:
      '512':
        rate: 0.022
        disk: 20
      '1024':
        rate: 0.06
        disk: 40
      '2048':
        rate: 0.12
        disk: 80
      '4096':
        rate: 0.24
        disk: 160
      '8192':
        rate: 0.48
        disk: 320
      '15872':
        rate: 0.90
        disk: 620
      '30720':
        rate: 1.20
        disk: 1200

    windows:
      '1024':
        rate: 0.08
        disk: 40
      '2048':
        rate: 0.16
        disk: 80
      '4096':
        rate: 0.32
        disk: 160
      '8192':
        rate: 0.58
        disk: 320
      '15872':
        rate: 1.08
        disk: 620
      '30720':
        rate: 1.56
        disk: 1200

    cloud_db:
      '512':
        rate: 0.06
      '1024':
        rate: 0.115
      '2048':
        rate: 0.21
      '4096':
        rate: 0.40


  # Presets...
  Presets =
    one: -> [
        {kind: 'server', quantity: 1, ram_size: 1024}
      ]
    two: -> [
        {kind: 'server', quantity: 1, ram_size: 1024}
        {kind: 'load_balancer'}
      ]
    three: -> [
        {kind: 'server', quantity: 1, ram_size: 1024}
        {kind: 'database', quantity: 1, ram_size: 2048}
        {kind: 'load_balancer'}
      ]
    four: -> [
        {kind: 'server', quantity: 1, ram_size: 1024}
        {kind: 'server', quantity: 1, ram_size: 1024}
        {kind: 'database', quantity: 1, ram_size: 2048}
        {kind: 'load_balancer'}
      ]
    five: -> [
        {kind: 'server', quantity: 1, ram_size: 1024}
        {kind: 'server', quantity: 1, ram_size: 1024}
        {kind: 'database', quantity: 1, ram_size: 2048}
        {kind: 'database', quantity: 1, ram_size: 2048}
        {kind: 'load_balancer'}
      ]

  # Our Event dispatcher
  class Vent extends Backbone.Events


  # Item Models
  class LoadBalancer extends Backbone.Model
    defaults:
      quantity: 1
      kind: 'load_balancer'
      connections: 100
      hours: 730
      ssl: false

    price: ->
      rate = if @get('ssl') then 0.05 else 0.015
      @get('quantity') * (rate * @get('hours')) + (@get('connections') * (0.00015 * @get('hours')))

    
  class Server extends Backbone.Model
    defaults: ->
      quantity: 1
      ram_size: 512
      hours: 730
      redhat: false
      os: 'linux'

    rate: ->
      Pricing[@get 'os'][@get 'ram_size'].rate

    price: ->
      @get('quantity') * (@rate() * @get('hours')) + if @get('redhat') then 20 else 0


  class Database extends Server
    defaults: ->
      _.defaults
        db_type: 'cloud_server'
      , super()

    initialize: ->
      # Remove the redhat attr inherited form Server
      @unset 'redhat', silent: true

    rate: ->
      os = @get 'os'
      if @get('db_type') is 'cloud_db'
        os = 'cloud_db'
      Pricing[os][@get 'ram_size'].rate

    price: ->
      @get('quantity') * (@rate() * @get('hours')) #+ if @get('db_type') is 'cloud_db' then (@get('disk_size') * 0.75) else 0


  class Managed extends Backbone.Model
    defaults:
      quantity: 1

    price: ->
      return 100


  class Bandwidth extends Backbone.Model
    defaults:
      quantity: 1

    price: ->
      0.18 * @get 'quantity'


  class Storage extends Backbone.Model
    defaults:
      quantity: 1
      storage_type: 'cloud_files'
      disk_size: 100

    price: ->
      rate = 0.10
      rate * @get('disk_size')

  class Backup extends Backbone.Model
    defaults:
      quantity: 1

    price: ->
      managed = @collection.find (item) -> item.get('kind') is 'managed_service'
      if !!managed then 0 else 10

  class Monitor extends Backbone.Model
    defaults:
      quantity: 1
      zone1: 0
      zone4: 0
      zone5: 0

    price: ->
      zones = [@get('zone1'), @get('zone4'), @get('zone5')]
      managed = @collection.find (item) -> item.get('kind') is 'managed_service'
      if !!managed
        free = 8
        zones = _.map zones, (num) ->
          result = num - free
          free   = if free - num < 0 then 0 else free - num
          if result < 0 then 0 else result

      (1.5 * zones[0]) + (2.0 * zones[1]) + (2.5 * zones[2])

  # Collection of Item Models
  class ItemCollection extends Backbone.Collection

    model: (attrs, options) ->
      # What kind of model are we dealing with...
      switch attrs.kind
        when "load_balancer" then new LoadBalancer attrs, options
        when "server" then new Server attrs, options
        when "database" then new Database attrs, options
        when "storage" then new Storage attrs, options
        when "bandwidth" then new Bandwidth attrs, options
        when "managed_service" then new Managed attrs, options
        when "backup" then new Backup attrs, options
        when "monitoring" then new Monitor attrs, options
        else throw "No model defined for #{ attrs.kind }."

    initialize: ->
      Vent
        .on('app:item:remove', @remove, @)
        .on('app:item:add', @add, @)
        .on('app:item:save', @updateItem, @)

    updateItem: (model, options) ->
      model.set(options)

    getGrandTotal: ->
      @reduce (memo, item) ->
        item.price() + memo 
      , 0

  class ItemsSubset extends Backbone.Subset
    initialize: (models, options) ->
      @kind = options.kind || 'server'
      @parent = options.parent
      
      Vent
        .on('app:item:remove', @remove, @)

    parent: -> @parent
    sieve: (item) ->
      if _.isString @kind
        item.get('kind') is @kind
      else if _.isArray @kind
        for k in @kind
          return true if item.get('kind') is k
      else
        throw "Invalid kind. Must be string or array."

  # Singular Item Model view
  class ItemView extends Backbone.View
    tagName: 'li'
    className: 'item'

    events:
      'keyup .quantity': 'update'
      'blur .quantity': 'update'

    template: _.template $('#item').html()

    initialize: ->
      @kind = @model.get 'kind'

      @model
        .on('add', @render, @)
        .on('change', @setSizePrice, @)
        .on('remove', @remove, @)

    render: ->
      @$el.html @template @model.toJSON()
      @$('.type').text titlize @kind
      @setSizePrice()
      if @kind is 'managed_service' or @kind is 'storage' or @kind is 'monitoring' or @kind is 'backup'
        @$('.quantity').attr('disabled', 'disabled')
      return this

    setSizePrice: ->
      
      @$('.size').text displaySize(@model.get('ram_size')) if @model.has 'ram_size'

      @$('.price').text toCurrency @model.price()
      @$('.quantity').val @model.get('quantity')

    update: (e) ->
      val = @$('.quantity').val()
      if (!val or val is '0') && (e.keyCode is 13 || e.type is 'focusout')
        # Trigger remove and pass model as argument
        Vent.trigger 'app:item:remove', @model
      else if e.keyCode is 13 || e.type is 'focusout'
        @saveModel(val)

    saveModel: (val) ->
      if _.isNumber(parseInt(val)) and _.isFinite(parseInt(val))
        @model.set quantity: parseInt(val)
      else
        @$('.quantity').val @model.get 'quantity'

  # Cart view of Item Collection
  class CartView extends Backbone.View

    initialize: ->
      @collection
        .on('add', @addOne, @)
        .on('reset', @addAll, @)
        .on('all', @render, @)
    
    render: ->
      checkEmpty @collection.isEmpty()
      return this

    addAll: ->
      @$('.itemized').html('')
      @collection.forEach (item) ->
        @addOne item
      , this

    addOne: (item) ->
      view = new ItemView model: item
      @$('.itemized').append view.render().$el



  # Column Views
  class ColumnView extends Backbone.View

    events:
      'click .add': 'newItem'
      'click .item': 'editItem'
      'click button.add-on': 'newAddOn'
    initialize: ->
      @kind = @$el.attr 'id'

      if @kind is 'add_on'
        @kind = ['storage', 'monitoring', 'backup']

      if !@collection
        @collection = new ItemsSubset [],
          kind: @kind
          parent: @options.parent

      @collection.on 'add change remove', @render, @

      @collection.liveupdate_keys = 'all'

      Vent.on('app:holder:remove', @cancelNew, @)

    render: ->
      @addAll()
      return this
 
    addAll: ->
      itemized = @$('.itemized')
      itemized.children().remove()
      @$('.itemized-left').remove()
      @$el.removeClass 'split'
      
      @totalQuantity = @collection
        .map (item, k) ->
          item.get('quantity')
        .reduce (memo, num) ->
          memo + num
        , 0

      @length = 0
      @collection.forEach (item, i) =>
        quantity = item.get 'quantity'
        if quantity > 1 and @totalQuantity <= 10
          while quantity--
            @addItem item
            @length++
        else
          @addItem item
          @length++

      @center()

    addItem: (item) ->
      quantity = item.get('quantity')

      if item.has('ram_size')
        desc = displaySize item.get('ram_size')

      elem = $ "<li class='item#{if @totalQuantity > 10 then ' many' else ''}#{if desc then ' desc' else ''} #{ item.get 'kind' }' data-quantity='#{ quantity }' data-cid='#{ item.cid }' #{ if desc then 'data-desc="'+desc+'"' } style='z-index: #{ @length + 1 };' />"
      
      if @length is 5
        @$('.itemized').addClass('itemized-left').removeClass('itemized')
        @$el.append $('<div class="itemized" />')
        @$el.addClass 'split'
        @center(@$('.itemized-left'))

      else if @$('itemized-left')[0] && @length < 5
        @$('.itemized').remove()
        @$('itemized-left').addClass('itemized').removeClass('itemized-left')

      @$('.itemized').prepend elem

    editItem: (e) ->
      elem = $(e.target)
      model = @collection.getByCid elem.attr('data-cid')
      Vent.trigger 'app:modal:open', model, @collection, elem

    newItem: (e) ->
      e.preventDefault()
      $('.calc-modal').hide()
      kind = $(e.target).attr('data-kind')

      itemized = @$('.itemized')
      elem = $ "<li class='item holder' style='z-index: #{ itemized.children().length + 1 };'>"
      itemized.prepend elem

      @center()
      checkEmpty false

      if @collection.last() and _.isString @kind
        model = @collection.last().clone()
      else
        model = @collection.model {kind: kind}

      Vent.trigger 'app:modal:open', model, @collection, elem

    newAddOn: (e) ->
      e.preventDefault()
      $target = $(e.target)
      $target.siblings('.calc-modal').show()

    cancelNew: (elem) ->
      elem.remove()
      @center()

    center: (elem = @$('.itemized')) ->
      top = (elem.height() / 2) + 35
      elem.css('margin-top', (top * -1))


  class ModalView extends Backbone.View

    tagName: 'form'
    id: 'edit_modal'
    className: 'calc-modal'

    events:
      'click button.save': 'saveModel'
      'click button.delete': 'deleteModel'
      'click a.close-btn': 'derender'
      'click a.toggle-advanced': 'toggleAdvanced'
      'slide #ram_size.slide': 'ramSizeSlider'
      'slide #disk_size.slide': 'diskSizeSlider'
      'slidechange #ram_size.slide': 'ramSizeSlider' # These are set twice incase of OS change.
      'slidechange #disk_size.slide': 'diskSizeSlider'
      'change #os': 'changeOS'

    template: _.template $('#modal').html()

    initialize: (options) ->
      @ramz = _.keys(Pricing.linux)

      @new = options.isNew
      @elem = options.elem

      Vent.on('app:modal:close', @derender, @)

      # Wrapped in a set timeout so it doesn't fire as the modal is opening.
      setTimeout ->
        $('html').bind 'click', (e) =>
          @$('button.save').click()
      , 1

      @$el.bind 'click', (e) =>
        e.stopPropagation()

      @render()


    render: ->

      @kind = @model.get('kind')
      attrs = @model.toJSON()

      @$el.html @template attrs

      @$('h3.kind').text(titlize(@kind))

      @position()

      $('body').append @$el

      # Set up sliders.
      if @kind is 'database' or @kind is 'server'
        size = @model.get('ram_size')
        ram_value = _.indexOf(@ramz, size.toString())
        @$('#ram_size.slide').slider({step: 1, min: 0, max: 6, value: ram_value})
        measure = ' MB'
        if size > 512
          measure = ' GB'
          size = Math.floor(size * 0.001)
        @$('.size').text(size + measure)

      else if @kind is 'storage'
        disk_value = @model.get('disk_size')
        @$('#disk_size.slide').slider({min: 0, max: 1000, value: disk_value})
        @$('.disk-size').text(disk_value + ' GB')

      return this


    derender: ->
      # Trigger remove on our columns placeholder element.
      if @new then Vent.trigger 'app:holder:remove', @elem

      $('html').unbind 'click'
      @$el.unbind 'click'

      @remove()

    ramSizeSlider: (e, ui) ->
      size = @ramz[ui.value]
      measure = ' MB'
      if size > 512
        measure = ' GB'
        size = Math.floor(size * 0.001)
      @$('.size').text(size + measure)

    diskSizeSlider: (e, ui) ->
      @$('.disk-size').text(ui.value + ' GB')

    changeOS: (e) ->
      os = $(e.target).val().toLowerCase()
      if os is 'windows'
          
        @$('#ram_size.slide').slider({min: 1, max: 6})
        if @$('#ram_size.slide').slider('value') is 1
          @$('#ram_size.slide').slider('value', 1)

        if @kind is 'server'
          @$('.advanced').hide()
          @$('#redhat').removeAttr('checked')

      else if os is 'linux'
        @$('#ram_size.slide').slider({min: 0, max: 6})

        if @kind is 'server'
          @$('.advanced').show()

    position: ->
      offset = @elem.offset()
      @$el.css
        'top': (offset.top - 55)
        'left': if (@kind is 'load_balancer') then (offset.left + 180) else (offset.left - 200)

      if (@kind is 'load_balancer')
        @$el.addClass('on-right')
      else
        @$el.removeClass('on-right')

      return this

    config: ->
      options = {}

      # Text inputs
      if @$('#hours') then options.hours = parseInt @$('#hours').val()
      if @$('#connections') then options.connections = parseInt @$('#connections').val()

      # Slides
      if @$('#ram_size')
        index = @$('#ram_size').slider('value')
        options.ram_size = parseInt @ramz[index]
      if @$('#disk_size') then options.disk_size = parseInt @$('#disk_size').slider('value')

      # Toggles
      if @$('#ssl') then options.ssl = @$('#ssl').attr('checked')
      if @$('#redhat') then options.redhat = @$('#redhat').attr('checked')
      if @$('#daas') then options.daas = @$('#daas').attr('checked')

      # Radio
      if @$('#cloud_db').attr('checked')
        options.db_type = 'cloud_db'
      else if @$('#cloud_server').attr('checked')
        options.db_type = 'cloud_server'

      # Selects
      if @$('#os') then options.os = @$('#os').val()


      # Delete undefined, null, and NaN keys
      for k, v of options
        if _.isNaN(v) or _.isUndefined(v) or _.isNull(v)
          delete options[k]
  
      return options

    saveModel: (e) ->
      e.preventDefault()
      options = @config()

      @model.set options, silent: true

      if @new
        last = @collection.last()
        if last && _.isEqual @model.toJSON(), last.toJSON()
          q = parseInt(last.get('quantity')) + 1
          Vent.trigger 'app:item:save', last, {quantity: q}
        else
          @model.set {quantity: 1}, silent: true
          Vent.trigger 'app:item:add', @model
      else
        @model.set @model.previousAttributes(), silent: true
        Vent.trigger 'app:item:save', @model, options

      $('.preset-options ul').removeAttr('class')
      $('.preset-options ul button').removeClass('selected')

      Vent.trigger 'app:modal:close'


    deleteModel: (e) ->
      e.preventDefault()
      if not @new then Vent.trigger 'app:item:remove', @model
      @elem.remove() if @elem
      Vent.trigger 'app:modal:close'


    toggleAdvanced: (e) ->
      e.preventDefault()
      @$('.advanced .wrap').slideToggle()
      @$('.advanced').toggleClass('open')




  # The grand App view
  class AppView extends Backbone.View

    events:
      'click .restart': 'resetCollection'
      'click .preset-options .option': 'setPreset'
      'change #managed-service': 'setManaged'
      'slide .bandwidth .slider': 'updateBandwidth'
      'click .calc_tooltip a.close-btn': 'closeTooltip'

    initialize: ->

      cartView         = new CartView({el: '#cart_list', collection: @collection})
      loadBalancerView = new ColumnView({el: '#load_balancer', parent: @collection})
      serverView       = new ColumnView({el: '#server', parent: @collection})
      databaseView     = new ColumnView({el: '#database', parent: @collection})
      addOnView        = new ColumnView({el: '#add_on', parent: @collection})


      Vent.on('app:modal:open', @openModal, @)

      @collection.on('all', @updateGrandTotal, @)

      @managedView = @$('#managed-service')
      @bandwidthView = @$('.bandwidth .slider')

      @render()

    render: ->
      @bandwidthView.slider({max: 1000})

    updateGrandTotal: ->
      totalView = @$('.total .amount')
      amount = @collection.getGrandTotal()
      totalView.text toCurrency amount, ''

      if totalView.text().length > 7
        totalView.css 'font-size', '22px'
      else
        totalView.attr 'style', ''


    openModal: (mod, col, el) ->
      isNew = if mod.collection then false else true
      new ModalView model: mod, collection: col, elem: el, isNew: isNew


    setPreset: (e) ->
      if @confirmReset()
        preset = $(e.target).parent().attr('data-preset')
        @resetCollection()
        $(e.target).parent().parent().addClass(preset)
        $(e.target).addClass('selected')
        @collection.add Presets[preset]()


    setManaged: ->
      managed_item = @collection.find (item) -> item.get('kind') is 'managed_service'
      
      if @managedView.attr('checked') and not managed_item
        Vent.trigger 'app:item:add', {kind: 'managed_service'}
      else
        Vent.trigger 'app:item:remove', managed_item


    updateBandwidth: (e, ui) ->
      bandwidth_item = @collection.find (item) -> item.get('kind') is 'bandwidth'
      bandwidth = ui.value

      if !bandwidth_item
        Vent.trigger 'app:item:add', {kind: 'bandwidth', quantity: bandwidth}
      else
        Vent.trigger 'app:item:save', bandwidth_item, {quantity: bandwidth}

      $('.bandwidth .slider-wrap label').text(bandwidth_item.get('quantity') + ' GB')


    resetCollection: ->
      @collection.reset()
      $('.preset-options ul').removeAttr('class')
      $('.preset-options ul button').removeClass('selected')


    confirmReset: (msg = 'This will clear your current configuration.') ->
      if not @collection.isEmpty()
        window.confirm(msg)
      else
        return true


    closeTooltip: (e) ->
      tooltip = $(e.target).parent().parent()
      tooltip.fadeOut ->
        tooltip.remove()


  # Helper functions

  displaySize = (size) ->
    size = parseInt size
    measure = ' MB'
    if size > 512
      measure = ' GB'
      size = Math.floor(size * 0.001)

    size + measure

  checkEmpty = (empty) ->
    if empty
      $('.item-list, .cart-list').addClass('empty')
    else
      $('.item-list, .cart-list').removeClass('empty')
      $('.preset-wrap .calc_tooltip').remove()


  toCurrency = (num, cur = '$') ->
    cur + parseFloat(num).toFixed(2)


  titlize = (title) ->
    title.replace('_', ' ').replace /\w\S*/g, (word) ->
      word.charAt(0).toUpperCase() + word.substr(1).toLowerCase()


  betterFocus = ->
    that = $(@)
    that.focus()
    if @setSelectionRange
      len = that.val().length * 2 #Opera bug
      @setSelectionRange len, len
    else
      that.val(that.val())


$ ->

  calcApp = new CalcApp()
