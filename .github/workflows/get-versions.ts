/* eslint-disable @typescript-eslint/no-unused-vars */
import {from, Observable, merge, throwError, of} from 'rxjs'
import {catchError, map} from 'rxjs/operators'
import {Octokit} from '@octokit/rest'
import {RestEndpointMethodTypes} from '@octokit/plugin-rest-endpoint-methods/dist-types/generated/parameters-and-response-types'

export interface RestVersionInfo {
  id: number
  version: string
  created_at: string
  tagged: boolean
}

export interface RestQueryInfo {
  versions: RestVersionInfo[]
  page: number
  paginate: boolean
  totalCount: number
}

type PackageType =
  RestEndpointMethodTypes['packages']['getAllPackageVersionsForPackageOwnedByUser']['parameters']['package_type']
type GetVersionsResponse =
  RestEndpointMethodTypes['packages']['getAllPackageVersionsForPackageOwnedByUser']['response']['data']

export function getOldestVersions(
  owner: string,
  packageName: string,
  packageType: string,
  numVersions: number,
  page: number,
  token: string
): Observable<RestQueryInfo> {
  const octokit = new Octokit({
    auth: token,
    baseUrl: process.env.GITHUB_API_URL || 'https://api.github.com'
  })
  const package_type: PackageType = packageType as PackageType

  return from(
    octokit.rest.packages.getAllPackageVersionsForPackageOwnedByUser({
      package_type,
      package_name: packageName,
      username: owner,
      per_page: numVersions,
      page
    })
  ).pipe(
    catchError(err => {
      const msg = 'get versions API failed.'
      return throwError(
        err.errors && err.errors.length > 0
          ? `${msg} ${err.errors[0].message}`
          : `${msg} ${err.message}`
      )
    }),
    map(response => {
      const resp = {
        versions: response.data.map((version: GetVersionsResponse[0]) => {
          let tagged = false
          if (
            package_type === 'container' &&
            version.metadata &&
            version.metadata.container
          ) {
            tagged = version.metadata.container.tags.length > 0
          }

          return {
            id: version.id,
            version: version.name,
            created_at: version.created_at,
            tagged
          }
        }),
        page,
        paginate: response.data.length === numVersions,
        totalCount: response.data.length
      }
      return resp
    })
  )
}
