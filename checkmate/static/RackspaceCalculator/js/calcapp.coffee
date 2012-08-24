# HALP Functions
########################

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

decode = (save) ->
  if window.atob
    b64 = save.slice(6)
    window.atob b64

encode = (json) ->
  if window.btoa
    '?cart=' + window.btoa JSON.stringify(json)


( ($) ->

  $.fn.toolTip = (tip) ->

    this.each ->

      $tooltip = $('<div class="calc_tooltip"><div><a class="close-btn" href="#">&times;</a><p /></div></div>')
      tip = tip || $(@).attr('data-tip')

      $tooltip.find('p').text(tip)
      
      close = (e) =>
        e.preventDefault()
        $(@).unbind 'mouseleave'
        $tooltip.find('.close').unbind 'click'
        $tooltip.fadeOut ->
          $(@).remove()

      open = =>
        $(@).after($tooltip)
        $(@).bind 'mouseleave', close
        $tooltip.find('.close-btn').bind 'click', close

      open()

)(jQuery)


# Models
########################

class Item extends Backbone.Model
  defaults: -> quantity: 1

  title: ->
    title = titlize @get 'kind'
    if @get('kind') is 'bandwidth' or @get('kind') is 'storage'
      title + ' (GB)'
    else
      title

  size: -> return ''
  clear: -> @destroy()


# Each model has slightly different calculations.
class LoadBalancer extends Item
  rate: -> if @get('ssl') then 0.05 else 0.015
  price: ->
    @get('quantity') * (@rate() * @get('hours')) + (@get('connections') * (0.00015 * @get('hours')))

class Server extends Item
  rate: -> Kinds.rates[@get 'os'][@get 'ram_size'][0]
  price: ->
    @get('quantity') * (@rate() * @get('hours')) + (if @get('redhat') then 20 else 0)
  size: -> @get 'ram_size'
  disk_size: -> Kinds.rates[@get 'os'][@get 'ram_size'][1]

class Database extends Item
  rate: ->
    os = @get 'os'
    ram_size = @get 'ram_size'
    if @get('daas')
      os = 'cloud_db'
      ram_size = if ram_size > 4096 then 4096 else if ram_size < 512 then 512 else @get('ram_size')

    Kinds.rates[os][ram_size][0]
  price: ->
    @get('quantity') * (@rate() * @get('hours')) + if @get('daas') then (@disk_size() * 0.75) else 0
  size: -> @get('ram_size')
  disk_size: ->
    if @get 'daas'
      @get 'disk_size'
    else
      Kinds.rates[@get 'os'][@get 'ram_size'][1]

class Storage extends Item
  rate: 0.10
  price: -> @rate * @get('disk_size')

class Bandwidth extends Item
  rate: 0.18
  price: -> @rate * @get('quantity')

class Managed extends Item
  price: -> return 100



# Collections
########################
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
      else new Item attrs, options

  # Set up localStorage
  localStorage: new Store 'rack-calc-dev'

  getGrandTotal: ->
    @reduce (memo, item) ->
      item.price() + memo 
    , 0

class ItemsSubset extends Backbone.Subset
  initialize: (models, options) ->
    @kind = options.kind || 'server'
    @parent = options.parent

  parent: -> @parent
  sieve: (item) -> item.get('kind') is @kind



# Views
########################

# Singular Item
class ItemView extends Backbone.View
  tagName: 'li'
  className: 'item'

  template: _.template $('#item').html()

  events:
    'click': 'edit'

  initialize: (bool) ->
    @model
      .on('change', @render, @)
      .on('destroy', @remove, @)

    # So CartItemView can pass over this binding later...
    if !!bool
      Dispatcher.on('openModal', @edit, @)

  render: ->
    $('.clone').remove()
    @$el.html @template @model.toJSON()

    # Hide quantity labels if there is only one
    if (@model.get('quantity') < 2)
      @$('label.quantity').hide()
    else
      @$('label.quantity').show()

    return @

  update: ->
    # Set Variable attributes.
    # Gets called from the CartItemView
    kind = @model.get('kind')
    size = @model.size()
    measure = ' MB'

    if size > 512
      measure = ' GB'
      size = Math.floor(size * 0.001)

    if kind is 'bandwidth' or kind is 'storage' or kind is 'managed_service' 
      measure = ''
    
    
    @model.set
      price: @model.price()
      display_size: size + measure
      display_price: toCurrency(@model.price())
      display_kind: @model.title()
    , silent: true

  edit: ->
    # Make a new Modal
    modal = new ModalView
      model: @model
      offset: @$el.offset()

  clear: ->
    @model.clear()
    @remove()


# Cart Singular Item
class CartItemView extends ItemView
  events:
    'keyup .quantity': 'updateOnKeyup'

  # Call initialize but pass option as false
  # Keeps our Modals from binding to these views.
  initialize: ->
    super false

  render: ->
    # We're calling update here because this cart view uses the 
    # master collection and will notify the others of an update anyways.
    @update()

    @$el.html @template @model.toJSON()
    @input = @$('input.quantity')
    return @

  # Update the model quantity on key up.
  updateOnKeyup: (e) ->
    val = @input.val()
    if (!val or val is '0') && e.keyCode is 13
      @clear()
    else
      @model.set quantity: val
      betterFocus.call @input




# Item list
class ItemListView extends Backbone.View
  events:
    'click button.add': 'incrementLastOne'

      
  initialize: () ->
    # Lets set this kind
    @kind = @$el.attr 'id'

    # Initialize our collection now if it doesn't exist.
    if !@collection
      @collection = new ItemsSubset [],
        kind: @kind
        parent: @options.parent

    # Okay, now bind to our collection
    @collection
      .on('add', @addOne, @)
      .on('reset', @addAll, @)
      .on('all', @render, @)
      
    @collection.liveupdate_keys = 'all'

  render: ->
    length = @collection.length

    # Split if colection is greater than 5
    if length > 5 then @$el.addClass 'split' else @$el.removeClass 'split'

    return @

  # Add all the items on a 'reset' event
  addAll: ->
    @collection.forEach (item) ->
      @addOne item
    , @

  # Add an item on and 'add' event
  addOne: (item) ->
    view = new ItemView model: item

    @$('.itemized')
      .prepend view.render().$el.css 'z-index', @nextOrder(item)
    
    # Center out list. 
    @center @$('.itemized')

  # Increment unless collection empty
  incrementLastOne: ->
    if @collection.last()
      last = @collection.last()
      oldQuantity = last.get 'quantity'
      last.set 'quantity', oldQuantity + 1



    else
      @createNew()

    # Trigger custom event to open a modal.
    Dispatcher.trigger 'openModal'

  # Create a new item.
  createNew: ->
    length = @collection.length
    # Dont allow more than one Storage
    if @kind is 'storage' and length >=1 then return false
    # Dont allow mroe than ten different kinds of configuartions
    if length >= 10 then return false

    # If there is a last item, use it's configuration
    # Otherwise make a new one from defaults.
    if @collection.last()
      last = @collection.last()
      @collection.add last.clone()

    else
      @collection.add Kinds[@kind]
    

  center: (elem)->
    top = (elem.height() / 2) + 35
    elem.css('margin-top', (top * -1))

  nextOrder: ->
    @collection.length + 1

  getQuantityTotal: ->
    @collection.reduce (memo, item) ->
      item.get('quantity') + memo 
    , 0


# Cart item list
class CartListView extends ItemListView
  # Not so DRY...
  render: ->
    if @collection.length <= 0 
      $('.item-list, .cart-list').addClass 'empty'
    else
      $('.item-list, .cart-list').removeClass 'empty'
      $('.preset-wrap .calc_tooltip').remove()

  # Override's addOne, uses different View, 
  # and appends rather than prepends.
  addOne: (item) ->
    view = new CartItemView model: item
    @$('.itemized').append(view.render().el)



# Modals
class ModalView extends Backbone.View
  tagName: 'form'
  id: 'edit_modal'
  events:
    'click .save': 'update',
    'click .delete': 'delete',
    'click .close-btn': '_close'
    'click a.toggle-advanced': 'toggleAdvanced'

  template: _.template($('#modal').html())

  initialize: ->
    @offset = @options.offset
    # Probably a better way, but remove any previous Modals.
    $('form#edit_modal').remove()
    # So we can convert ram_sizes to an index for jQuery-ui slider.
    @ramz = _.keys(Kinds.rates.linux)

    # Just render, no need to bind to the model.
    @render()

  render: ->
    @$el.html @template @model.toJSON()

    # Set up sliders.
    ram_value = _.indexOf(@ramz, @model.get('ram_size'))
    disk_value = @model.get('disk_size') || 0
    @$('#ram_size.slide').slider({step: 1, min: 0, max: 7, value: ram_value})
    @$('#disk_size.slide').slider({min: 0, max: 1000, value: disk_value})

    @$el.css
      'top': (@offset.top - 55)
      'left': if (@model.get('kind') is 'load_balancer') then (@offset.left + 180) else (@offset.left - 200)

    if (@model.get('kind') is 'load_balancer')
      @$el.addClass('on-right')

    @$('#ram_size.slide').bind 'slide', (e, ui) =>
      size = @ramz[ui.value]
      measure = ' MB'
      if size > 512
        measure = ' GB'
        size = Math.floor(size * 0.001)

      @$('#ram_size.slide').siblings('i').text(size + measure)

    @$('#disk_size.slide').bind 'slide', (e, ui) =>
      @$('#disk_size.slide').siblings('i').text(ui.value + ' GB')

    @$('#daas').bind 'change', =>
      @$('#disk_size').parent().toggle()
      @$('#db_type').parent().toggle()

    $('body').append @$el

    return @

  # Save the model
  update: (e) ->
    e.preventDefault()
    options = {}

    # Text inputs
    if @$('#hours') then options.hours = @$('#hours').val()
    if @$('#connections') then options.connections = @$('#connections').val()

    # Slides
    if @$('#ram_size')
      index = @$('#ram_size').slider('value')
      options.ram_size = @ramz[index]
    if @$('#disk_size') then options.disk_size = @$('#disk_size').slider('value')

    # Toggles
    if @$('#ssl') then options.ssl = @$('#ssl').attr('checked')
    if @$('#redhat') then options.redhat = @$('#redhat').attr('checked')
    if @$('#daas') then options.daas = @$('#daas').attr('checked')

    # Selects
    if @$('#os') then options.os = @$('#os').val()
    if @$('#db_type') then options.db_type = @$('#db_type').val()

    @model.set options

    @_close(e)

  toggleAdvanced: (e) ->
    e.preventDefault()
    @$('.advanced .wrap').slideToggle()
    @$('.advanced').toggleClass('open')

  delete: (e) ->
    e.preventDefault()
    @model.clear()
    @_close(e)

  _close: (e) ->
    e.preventDefault()
    @$el.remove()


# App
########################

class AppView extends Backbone.View

  events:
    'click .restart': 'resetConfig'
    'click .preset-options .option': 'setPreset'
    'slide .bandwidth .slider': 'updateBandwidth'
    'change #managed-service': 'setManaged'

  initialize: ->

    # Set up our subviews, and bind 
    # them to the elements already in the dom
    CartView = new CartListView({el: '#cart_list', collection: @collection})
    LoadView = new ItemListView({el: '#load_balancer', parent: @collection})
    ServerView = new ItemListView({el: '#server', parent: @collection})
    DatabaseView = new ItemListView({el: '#database', parent: @collection})
    StorageView = new ItemListView({el: '#storage', parent: @collection})

    # Bind to our collection.
    @collection.on 'all', @render, @

    $('.preset-wrap [data-preset=three] button').toolTip()
    @render()

  render: ->
    # Set the grand total
    totalView = @$('.total .amount')
    amount = @collection.getGrandTotal()
    totalView.text toCurrency amount, ''

    if totalView.text().length > 7
      totalView.css 'font-size', '22px'
    else
      totalView.attr 'style', ''


    # These really dont belong here...
    @managed_item = @collection.find (item) -> item.get('kind') is 'managed_service'
    @bandwidth_item = @collection.find (item) -> item.get('kind') is 'bandwidth'

    @managed = @$('#managed-service')
    @managed.attr 'checked', if @managed_item then true else false
    
    @$('.bandwidth .slider').slider({max: 1000})
    

    return @

  updateBandwidth: (e, ui) ->
    bandwidth = ui.value
    if !@bandwidth_item
      @collection.add
        kind: 'bandwidth'
        quantity: bandwidth
    else
      @bandwidth_item.set
        quantity: bandwidth

    $('.bandwidth .slider-wrap label').text(@bandwidth_item.get('quantity') + ' GB')

  setManaged: ->
    if @managed.attr('checked') and not @managed_item
      @collection.add
        kind: 'managed_service'
    else
      @managed_item.destroy()

  setPreset: (e) ->
    preset = $(e.target).parent().attr('data-preset')
    @resetConfig()
    $(e.target).parent().parent().addClass(preset)
    $(e.target).addClass('selected')
    @collection.add Presets[preset]()

  resetConfig: ->
    @collection.reset()
    $('.preset-options ul').removeAttr('class')
    $('.preset-options ul button').removeClass('selected')

    $('.itemized li, form#edit_modal').remove()
    if window.history
      window.history.pushState null, null, '/'

# Custom event dispatcher.
Dispatcher = _.extend {}, Backbone.Events



# Dom Ready
$ ->
  # Set up our initial collection and view.
  Items = new ItemCollection
  Calc = new AppView
    el: '#racker-calculator'
    collection: Items

  save = window.location.search
  if save
    save = JSON.parse(decode(save))
    save.forEach (item) ->
      Items.add(item)

  $('.calculator-actions .save').click ->
    if window.history
      window.history.pushState null, null, encode(Items.toJSON())




# Presets...
Presets =
  one: -> [
      _.extend Kinds.server, {quantity: 1, ram_size: 1024}
    ]
  two: -> [
      _.extend Kinds.server, {quantity: 1, ram_size: 1024}
      Kinds.load_balancer
    ]
  three: -> [
      _.extend Kinds.server, {quantity: 1, ram_size: 1024}
      _.extend Kinds.database, {quantity: 1, ram_size: 1024}
      Kinds.load_balancer
    ]
  four: -> [
      _.extend Kinds.server, {quantity: 1, ram_size: 1024}
      _.extend Kinds.server, {quantity: 1, ram_size: 1024}
      _.extend Kinds.database, {quantity: 1, ram_size: 1024}
      Kinds.load_balancer
    ]
  five: -> [
      _.extend Kinds.server, {quantity: 1, ram_size: 1024}
      _.extend Kinds.server, {quantity: 1, ram_size: 1024}
      _.extend Kinds.database, {quantity: 1, ram_size: 1024}
      _.extend Kinds.database, {quantity: 1, ram_size: 1024}
      Kinds.load_balancer
    ]

# Defaults
Kinds =
  server:
    kind: 'server'
    ram_size: 256
    hours: 730
    redhat: false
    os: 'linux'

  load_balancer:
    kind: 'load_balancer'
    connections: 100
    hours: 730
    ssl: false

  database:
    kind: 'database'
    os: 'linux'
    db_type: 'other'
    ram_size: 256
    hours: 730
    daas: false

  storage:
    kind: 'storage'
    storage_type: 'cloud_files'
    disk_size: 100

  rates:
    linux:
      '256': [0.015, 10]
      '512': [0.022, 20]
      '1024': [0.06, 40]
      '2048': [0.12, 80]
      '4096': [0.24, 160]
      '8192': [0.48, 320]
      '15872': [0.90, 620]
      '30720': [1.20, 1200]

    windows:
      '1024': [0.08, 40]
      '2048': [0.16, 80]
      '4096': [0.32, 160]
      '8192': [0.58, 320]
      '15872': [1.08, 620]
      '30720': [1.56, 1200]

    cloud_db:
      '512': [0.06]
      '1024': [0.115]
      '2048': [0.21]
      '4096': [0.40]