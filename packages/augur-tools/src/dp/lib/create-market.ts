import { Augur } from "@augurproject/sdk";
import { MarketData } from "../data/canned-markets";
import { BigNumber, Event } from "../types";
import { ethers } from "ethers";

export async function createMarket(
  augur: Augur<BigNumber>,
  market: MarketData,
  designatedReporterAddress:string
):Promise<Array<Event>> {
  switch (market.marketType) {
    case "categorical":
      return augur.contracts.universe.createCategoricalMarket(
        new BigNumber(market._endTime),
        new BigNumber(1000),
        new BigNumber(market._affiliateFeeDivisor),
        designatedReporterAddress,
        market._outcomes.map(ethers.utils.formatBytes32String),
        ethers.utils.formatBytes32String(market._topic),
        JSON.stringify(market._extraInfo)
      );
    case "scalar":
      return augur.contracts.universe.createScalarMarket(
        new BigNumber(market._endTime),
        new BigNumber(1000),
        new BigNumber(market._affiliateFeeDivisor),
        designatedReporterAddress,
        [
          new BigNumber(market._minPrice),
          new BigNumber(market._maxPrice)
        ],
        new BigNumber(market._numTicks),
        ethers.utils.formatBytes32String(market._topic),
        JSON.stringify(market._extraInfo)
      );
    case "yesNo":
    default:
      return augur.contracts.universe.createYesNoMarket(
        new BigNumber(market._endTime),
        new BigNumber(1000),
        new BigNumber(market._affiliateFeeDivisor),
        designatedReporterAddress,
        ethers.utils.formatBytes32String(market._topic),
        JSON.stringify(market._extraInfo)
      );
  }

}
