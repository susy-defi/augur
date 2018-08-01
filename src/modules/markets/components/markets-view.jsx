import React, { Component } from 'react'
import PropTypes from 'prop-types'
import { Helmet } from 'react-helmet'

import MarketsHeader from 'modules/markets/components/markets-header/markets-header'
import MarketsList from 'modules/markets/components/markets-list'
import isEqual from 'lodash/isEqual'
import { TYPE_TRADE } from 'modules/market/constants/link-types'
import {
  MARKET_RECENTLY_TRADED,
} from 'modules/filter-sort/constants/market-sort-params'
import {
  MARKET_OPEN,
} from 'modules/filter-sort/constants/market-states'

export default class MarketsView extends Component {
  static propTypes = {
    isLogged: PropTypes.bool.isRequired,
    loginAccount: PropTypes.object.isRequired,
    markets: PropTypes.array.isRequired,
    canLoadMarkets: PropTypes.bool.isRequired,
    hasLoadedMarkets: PropTypes.bool.isRequired,
    category: PropTypes.string,
    hasLoadedSearch: PropTypes.object.isRequired,
    loadMarkets: PropTypes.func.isRequired,
    loadMarketsByCategory: PropTypes.func.isRequired,
    loadMarketsBySearch: PropTypes.func.isRequired,
    location: PropTypes.object.isRequired,
    history: PropTypes.object.isRequired,
    tags: PropTypes.array,
    keywords: PropTypes.string,
    toggleFavorite: PropTypes.func.isRequired,
    loadMarketsInfoIfNotLoaded: PropTypes.func.isRequired,
    isMobile: PropTypes.bool,
    loadMarketsByFilter: PropTypes.func.isRequired,
  }

  constructor(props) {
    super(props)

    this.state = {
      filter: MARKET_OPEN,
      sort: MARKET_RECENTLY_TRADED,
      filterSortedMarkets: [],
      loadByMarkets: [],
    }

    this.updateFilter = this.updateFilter.bind(this)
    this.updateFilteredMarkets = this.updateFilteredMarkets.bind(this)
  }

  componentDidMount() {
    const {
      canLoadMarkets,
      category,
      hasLoadedSearch,
      tags,
      keywords,
      hasLoadedMarkets,
    } = this.props

    this.loadMarketsFn({
      canLoadMarkets,
      category,
      hasLoadedSearch,
      tags,
      keywords,
      hasLoadedMarkets,
    })
    this.updateFilteredMarkets()
  }

  componentDidUpdate(prevProps) {
    const {
      canLoadMarkets,
      category,
      hasLoadedSearch,
      tags,
      keywords,
      hasLoadedMarkets,
    } = this.props
    if (
      (category !== prevProps.category) ||
      (keywords !== prevProps.keywords) ||
      (tags !== prevProps.tags) ||
      (canLoadMarkets !== prevProps.canLoadMarkets && canLoadMarkets) ||

      !isEqual(hasLoadedSearch, prevProps.hasLoadedSearch)
    ) {
      this.loadMarketsFn({
        canLoadMarkets,
        category,
        hasLoadedSearch,
        tags,
        keywords,
        hasLoadedMarkets,
      })
    }
  }

  getMarketIdsBySearch(keywords, tagName) {
    this.props.loadMarketsBySearch(keywords, tagName, (err, marketIds) => {
      if (!err) this.setState({ loadByMarkets: marketIds })
    })
  }

  loadMarketsFn({ canLoadMarkets, category, hasLoadedSearch, tags, keywords, hasLoadedMarkets }) {
    if (!category && (!tags || tags.length === 0) && !keywords) {
      this.setState({ loadByMarkets: [] })
      if (!hasLoadedMarkets) this.updateFilteredMarkets()
    }
    if (canLoadMarkets) {
      if (category && !hasLoadedSearch[category]) {
        this.props.loadMarketsByCategory(category, (err, marketIds) => {
          if (!err) this.setState({ loadByMarkets: marketIds })
        })
      } else if (tags && tags.length > 0) {
        if (tags[0] && !hasLoadedSearch[tags[0]]) {
          this.getMarketIdsBySearch(tags[0], tags[0])
        }
        if (tags[1] && !hasLoadedSearch[tags[1]]) {
          this.getMarketIdsBySearch(tags[1], tags[1])
        }
      } else if (keywords && keywords.length > 3 && !hasLoadedSearch.keywords) {
        this.getMarketIdsBySearch(keywords, 'keywords')
      }
    }
  }

  updateFilter(params) {
    const { filter, sort } = params
    this.setState({ filter, sort }, this.updateFilteredMarkets)
  }

  updateFilteredMarkets() {
    const { filter, sort } = this.state
    this.props.loadMarketsByFilter({ filter, sort }, (err, filterSortedMarkets) => {
      if (err) return console.log('Error loadMarketsFilter:', err)
      this.setState({ filterSortedMarkets })
    })
  }

  render() {
    const {
      history,
      isLogged,
      isMobile,
      loadMarketsInfoIfNotLoaded,
      location,
      markets,
      toggleFavorite,
    } = this.props
    const s = this.state
    const filteredMarketsFinal = []
    if (s.filterSortedMarkets.length) {
      s.filterSortedMarkets.reduce((finalArray, marketId) => {
        if (s.loadByMarkets.includes(marketId)) {
          finalArray.push(marketId)
        } else if (s.loadByMarkets.length === 0) {
          finalArray.push(marketId)
        }
        return finalArray
      }, filteredMarketsFinal)
    }

    return (
      <section id="markets_view">
        <Helmet>
          <title>Markets</title>
        </Helmet>
        <MarketsHeader
          isLogged={isLogged}
          location={location}
          markets={markets}
          filter={s.filter}
          sort={s.sort}
          updateFilter={this.updateFilter}
        />
        <MarketsList
          testid="markets"
          isLogged={isLogged}
          markets={markets}
          filteredMarkets={filteredMarketsFinal}
          location={location}
          history={history}
          toggleFavorite={toggleFavorite}
          loadMarketsInfoIfNotLoaded={loadMarketsInfoIfNotLoaded}
          linkType={TYPE_TRADE}
          isMobile={isMobile}
        />
      </section>
    )
  }
}
